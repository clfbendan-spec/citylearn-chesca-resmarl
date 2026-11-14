package com.citylearn.building;

import com.citylearn.config.FileResourceProperties;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.*;
import java.util.*;
import java.util.stream.Collectors;

@Service
@DependsOn("buildingSchemaMigration")
public class BuildingIngestionService {
    @Resource private JdbcTemplate jdbc;
    @Resource private ObjectMapper mapper;
    @Resource private FileResourceProperties files;
    private final MeasurementContract contract = new MeasurementContract();

    public List<Map<String, Object>> list() {
        return jdbc.query("SELECT b.*, (SELECT COUNT(*) FROM building_measurement m WHERE m.building_id=b.id) sample_count,"
                        + " (SELECT MAX(timestamp_ms) FROM building_measurement m WHERE m.building_id=b.id) last_sample"
                        + " FROM managed_building b WHERE archived=0 AND NOT EXISTS (SELECT 1 FROM community_building cb"
                        + " JOIN managed_community c ON c.id=cb.community_id WHERE cb.building_id=b.id AND c.archived<>0) ORDER BY id DESC",
                (rs, n) -> {
                    Map<String, Object> row = decode(rs.getString("metadata"));
                    row.put("id", rs.getLong("id")); row.put("count", rs.getLong("sample_count"));
                    long last = rs.getLong("last_sample");
                    row.put("lastSample", rs.wasNull() ? null : Instant.ofEpochMilli(last).toString());
                    row.put("hasToken", rs.getString("token_hash") != null);
                    row.put("communityId", communityId(rs.getLong("id")));
                    return row;
                });
    }
    public Map<String, Object> get(long id, boolean lock) {
        if (lock) requireActiveCommunity(id);
        List<Map<String, Object>> rows = jdbc.query("SELECT * FROM managed_building WHERE id=? AND archived=0"
                + (lock ? " FOR UPDATE" : ""), (rs, n) -> {
                    Map<String, Object> row = decode(rs.getString("metadata"));
                    row.put("id", rs.getLong("id"));
                    row.put("hasToken", rs.getString("token_hash") != null);
                    row.put("communityId", communityId(rs.getLong("id")));
                    return row;
                }, id);
        if (rows.isEmpty()) throw new IllegalArgumentException("建筑不存在或已删除");
        return rows.get(0);
    }
    @Transactional
    public Map<String, Object> save(Long id, Map<String, Object> input) {
        input = new LinkedHashMap<>(input);
        Long owner = id == null ? null : communityId(id);
        if (input.get("communityId") != null) {
            long requested = Long.parseLong(input.get("communityId").toString());
            if (owner != null && owner != requested) throw new IllegalArgumentException("建筑已属于其他社区");
            owner = requested;
        }
        if (owner != null) {
            List<String> community = jdbc.query("SELECT metadata FROM managed_community WHERE id=? AND archived=0 FOR UPDATE", (rs,n)->rs.getString(1),owner);
            if (community.isEmpty()) throw new IllegalArgumentException("社区不存在或已删除");
            Map<String,Object> settings=decode(community.get(0));
            for (String field:List.of("timezone","currency","intervalSeconds","timestampKind")) {
                Object value=settings.get(field);
                if (input.containsKey(field) && !Objects.equals(input.get(field).toString(),value.toString()))
                    throw new IllegalArgumentException("建筑的时区、币种、采样周期和时间来源必须与社区一致: "+field);
                input.put(field,value);
            }
        }
        Map<String, Object> data = new LinkedHashMap<>();
        String name = text(input.get("name"));
        if (name.isEmpty() || name.length() > 120) throw new IllegalArgumentException("建筑名称应为 1–120 个字符");
        data.put("name", name);
        String timezone = text(input.getOrDefault("timezone", "Asia/Shanghai"));
        ZoneId.of(timezone); data.put("timezone", timezone);
        String timestampKind=text(input.getOrDefault("timestampKind","measured"));
        if(!List.of("measured","assigned").contains(timestampKind)) throw new IllegalArgumentException("请选择真实时间或约定时间轴");
        data.put("timestampKind",timestampKind);
        int interval = ((Number) input.getOrDefault("intervalSeconds", 3600)).intValue();
        if (!List.of(60, 300, 900, 1800, 3600).contains(interval)) throw new IllegalArgumentException("不支持的采样周期");
        data.put("intervalSeconds", interval);
        for (String key : List.of("address", "buildingType", "description", "currency")) {
            String value = text(input.get(key));
            if (value.length() > 1000) throw new IllegalArgumentException("字段过长: " + key);
            data.put(key, value);
        }
        if (input.containsKey("devices")) {
            Map<String,Object> devices = SchemaEquipment.normalize(input.get("devices"));
            data.put("devices", devices);
            Map<?,?> battery = devices.containsKey("electrical_storage") ? (Map<?,?>)((Map<?,?>)devices.get("electrical_storage")).get("attributes") : Map.of();
            data.put("batteryCapacity", battery.containsKey("capacity") ? battery.get("capacity") : 0.0);
            data.put("batteryPower", battery.containsKey("nominal_power") ? battery.get("nominal_power") : 0.0);
            double area = input.get("area") == null ? 0 : Double.parseDouble(input.get("area").toString());
            if (!Double.isFinite(area) || area < 0 || area > 1e8) throw new IllegalArgumentException("建筑面积超出范围");
            data.put("area", area);
        } else for (String key : List.of("batteryCapacity", "batteryPower", "batteryEfficiency", "pvPower",
                "coolingCop", "heatingCop", "dhwEfficiency", "area")) {
            double value;
            try { value = Double.parseDouble(input.getOrDefault(key, key.equals("area") ? 0 : "").toString()); }
            catch (NumberFormatException e) { throw new IllegalArgumentException("设备参数必填: " + key); }
            double min = List.of("pvPower", "area").contains(key) ? 0 : 0.0001;
            double max = List.of("batteryEfficiency", "dhwEfficiency").contains(key) ? 1
                    : List.of("coolingCop", "heatingCop").contains(key) ? 20 : 1e8;
            if (!Double.isFinite(value) || value < min || value > max) throw new IllegalArgumentException("设备参数超出范围: " + key);
            data.put(key, value);
        }
        if (id == null) {
            GeneratedKeyHolder key = new GeneratedKeyHolder();
            jdbc.update(connection -> {
                PreparedStatement ps = connection.prepareStatement("INSERT INTO managed_building(name,metadata) VALUES (?,?)",
                        Statement.RETURN_GENERATED_KEYS);
                ps.setString(1, name); ps.setString(2, encode(data)); return ps;
            }, key);
            id = Objects.requireNonNull(key.getKey()).longValue();
        } else {
            Map<String, Object> previous = get(id, true);
            long count = jdbc.queryForObject("SELECT COUNT(*) FROM building_measurement WHERE building_id=?", Long.class, id);
            if (count > 0 && (!previous.get("timezone").equals(timezone)
                    || ((Number) previous.get("intervalSeconds")).intValue() != interval))
                throw new IllegalArgumentException("已有数据的建筑不能修改时区或采样周期");
            jdbc.update("UPDATE managed_building SET name=?,metadata=? WHERE id=?", name, encode(data), id);
        }
        if (owner != null) jdbc.update("INSERT IGNORE INTO community_building(community_id,building_id) VALUES (?,?)",owner,id);
        return get(id, false);
    }
    private Long communityId(long id) {
        List<Long> owners=jdbc.query("SELECT community_id FROM community_building WHERE building_id=?",(rs,n)->rs.getLong(1),id);
        return owners.isEmpty()?null:owners.get(0);
    }
    private void requireActiveCommunity(long id) {
        Long owner = communityId(id);
        if (owner == null) return;
        // Lock the owner before its child, matching community archival and building saves.
        List<Long> active = jdbc.query("SELECT id FROM managed_community WHERE id=? AND archived=0 FOR UPDATE",
                (rs,n)->rs.getLong(1),owner);
        if (active.isEmpty()) throw new IllegalArgumentException("所属社区不存在或已删除，不能修改建筑或接入数据");
    }
    @Transactional public String rotateToken(long id) {
        get(id, true);
        byte[] bytes = new byte[32]; new java.security.SecureRandom().nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        jdbc.update("UPDATE managed_building SET token_hash=? WHERE id=?", hash(token), id);
        return token;
    }
    @Transactional public void deleteBuilding(long id) {
        get(id, true);
        if (jdbc.queryForObject("SELECT COUNT(*) FROM building_experiment_run WHERE building_id=? AND status IN ('queued','running')", Integer.class, id) > 0)
            throw new IllegalArgumentException("建筑有排队或运行中的任务，请先终止任务再删除");
        jdbc.update("UPDATE citylearn_dataset SET enabled=0 WHERE BINARY schema_key IN (SELECT BINARY schema_key FROM building_dataset_version WHERE building_id=?)", id);
        jdbc.update("UPDATE managed_building SET archived=1,token_hash=NULL WHERE id=?", id);
    }
    @Transactional public void deleteVersion(long id, String version) {
        get(id, true);
        if (jdbc.queryForObject("SELECT COUNT(*) FROM building_dataset_version v JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY v.schema_key AND d.enabled=1 WHERE v.id=? AND v.building_id=?", Integer.class, version, id) != 1)
            throw new IllegalArgumentException("数据集不存在或已删除");
        if (jdbc.queryForObject("SELECT COUNT(*) FROM building_experiment_run WHERE building_id=? AND version_id=? AND status IN ('queued','running')", Integer.class, id, version) > 0)
            throw new IllegalArgumentException("数据集有排队或运行中的任务，请先终止任务再删除");
        // Keep immutable files and experiment references for historical reproducibility.
        jdbc.update("UPDATE citylearn_dataset SET enabled=0 WHERE BINARY schema_key=(SELECT BINARY schema_key FROM building_dataset_version WHERE id=? AND building_id=?)", version, id);
    }
    public boolean authenticate(long id, String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) return false;
        List<String> stored = jdbc.query("SELECT b.token_hash FROM managed_building b WHERE b.id=? AND b.archived=0"
                        + " AND NOT EXISTS (SELECT 1 FROM community_building cb LEFT JOIN managed_community c ON c.id=cb.community_id"
                        + " WHERE cb.building_id=b.id AND (c.id IS NULL OR c.archived<>0))",
                (rs, n) -> rs.getString(1), id);
        return !stored.isEmpty() && stored.get(0) != null && java.security.MessageDigest.isEqual(
                stored.get(0).getBytes(StandardCharsets.UTF_8), hash(authorization.substring(7)).getBytes(StandardCharsets.UTF_8));
    }

    @Transactional
    public Map<String, Object> ingest(long id, List<Map<String, Object>> raw, Map<String, String> mapping,
                                       Map<String, String> units, String source) {
        return ingest(id,raw,mapping,units,source,List.of());
    }
    @Transactional
    public Map<String, Object> ingest(long id, List<Map<String, Object>> raw, Map<String, String> mapping,
                                       Map<String, String> units, String source,List<Map<String,String>> sourceFiles) {
        return ingest(id,raw,mapping,units,source,sourceFiles,null);
    }
    @Transactional
    public Map<String, Object> ingest(long id, List<Map<String, Object>> raw, Map<String, String> mapping,
                                       Map<String, String> units, String source,List<Map<String,String>> sourceFiles,String timestampKind) {
        Map<String, Object> building = get(id, true);
        boolean changeTimeKind=false;
        if(timestampKind!=null) {
            if(!List.of("measured","assigned").contains(timestampKind)) throw new IllegalArgumentException("请确认导入时间轴是真实测量还是约定时间");
            changeTimeKind=!timestampKind.equals(building.getOrDefault("timestampKind","measured"));
            if(changeTimeKind && communityId(id)!=null)
                throw new IllegalArgumentException("建筑时间来源必须与所属社区一致，请先核对社区时间轴配置");
            if(changeTimeKind && jdbc.queryForObject("SELECT COUNT(*) FROM building_measurement WHERE building_id=?",Long.class,id)>0)
                throw new IllegalArgumentException("不能混合真实时间和约定时间轴；请新建建筑或先核对并编辑建筑时间轴来源");
            building.put("timestampKind",timestampKind);
        }
        if (raw == null || raw.isEmpty() || raw.size() > 10000) throw new IllegalArgumentException("每批应为 1–10000 条");
        if (mapping == null) mapping = Map.of();
        if (units == null) units = Map.of();
        List<Map<String,Object>> originals=new ArrayList<>();
        long originalBytes=0;
        if(sourceFiles!=null) {
            if(sourceFiles.size()>8) throw new IllegalArgumentException("每批最多保留8个源CSV文件");
            for(Map<String,String> file:sourceFiles) {
                if(file==null || file.get("name")==null || !file.containsKey("content") && !file.containsKey("base64") || file.get("name").length()>255) throw new IllegalArgumentException("源文件信息无效");
                byte[] bytes;
                try {bytes=file.containsKey("base64")?Base64.getDecoder().decode(file.get("base64")):file.get("content").getBytes(StandardCharsets.UTF_8);}
                catch(RuntimeException error) {throw new IllegalArgumentException("源文件编码无效");}
                originalBytes+=bytes.length;
                if(bytes.length>20*1024*1024 || originalBytes>40*1024*1024) throw new IllegalArgumentException("单个源CSV最多20MB，每批源文件合计最多40MB");
                originals.add(Map.of("name",file.get("name"),"base64",Base64.getEncoder().encodeToString(bytes),"sha256",BuildingDatasetExporter.sha256(bytes)));
            }
        }
        ZoneId zone = ZoneId.of(building.get("timezone").toString());
        int interval = ((Number) building.get("intervalSeconds")).intValue();
        Map<Long, Map<String, Object>> normalized = new TreeMap<>();
        int duplicates = 0;
        for (int i = 0; i < raw.size(); i++) {
            Map<String, Object> row;
            try { row = contract.normalize(raw.get(i), zone, interval, mapping, units); }
            catch (RuntimeException e) { throw new IllegalArgumentException("第 " + (i + 1) + " 行: " + e.getMessage()); }
            long time = Instant.parse(row.get("timestamp").toString()).toEpochMilli();
            if (normalized.containsKey(time)) {
                if (!encode(normalized.get(time)).equals(encode(row))) throw new IllegalArgumentException("批次内同一时间有冲突: " + row.get("timestamp"));
                duplicates++;
            } else normalized.put(time, row);
        }
        List<Map.Entry<Long, Map<String, Object>>> pending = new ArrayList<>();
        List<Map.Entry<Long, Map<String, Object>>> updates = new ArrayList<>();
        for (Map.Entry<Long, Map<String, Object>> row : normalized.entrySet()) {
            List<String> previous = jdbc.query("SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms=?",
                    (rs, n) -> rs.getString(1), id, row.getKey());
            if (previous.isEmpty()) pending.add(row);
            else {
                Map<String, Object> old = decode(previous.get(0));
                for (Map.Entry<String, Object> field : row.getValue().entrySet()) {
                    if (old.containsKey(field.getKey()) && !old.get(field.getKey()).toString().equals(field.getValue().toString()))
                        throw new IllegalArgumentException("历史记录冲突，原记录已保留: " + row.getValue().get("timestamp") + " " + field.getKey());
                }
                if (old.keySet().containsAll(row.getValue().keySet())) duplicates++;
                else {
                    old.putAll(row.getValue());
                    Map<String, Object> merged = new LinkedHashMap<>();
                    merged.put("timestamp", old.get("timestamp"));
                    for (String key : MeasurementContract.FIELDS.keySet()) if (old.containsKey(key)) merged.put(key, old.get(key));
                    updates.add(new AbstractMap.SimpleEntry<>(row.getKey(), merged));
                }
            }
        }
        // All validation precedes writes, so even callers catching validation errors cannot observe a partial batch.
        if(changeTimeKind) {
            Map<String,Object> metadata=new LinkedHashMap<>(building);metadata.remove("id");metadata.remove("hasToken");
            jdbc.update("UPDATE managed_building SET metadata=? WHERE id=?",encode(metadata),id);
        }
        jdbc.batchUpdate("INSERT INTO building_measurement(building_id,timestamp_ms,payload,source) VALUES (?,?,?,?)",
                pending, 500, (ps, row) -> {
                    ps.setLong(1, id); ps.setLong(2, row.getKey());
                    ps.setString(3, encode(row.getValue())); ps.setString(4, source);
                });
        jdbc.batchUpdate("UPDATE building_measurement SET payload=?,source=? WHERE building_id=? AND timestamp_ms=?",
                updates, 500, (ps, row) -> {
                    ps.setString(1, encode(row.getValue())); ps.setString(2, source);
                    ps.setLong(3, id); ps.setLong(4, row.getKey());
                });
        String batchId = UUID.randomUUID().toString();
        String payload = encode(Map.of("rows", raw, "mapping", mapping, "units", units, "building", building,"sourceFiles",originals));
        jdbc.update("INSERT INTO building_ingestion_batch(id,building_id,source,raw_payload,payload_hash,accepted,duplicates)"
                        + " VALUES (?,?,?,?,?,?,?)", batchId, id, source, payload, hash(payload), pending.size() + updates.size(), duplicates);
        if ("realtime".equals(source)) HomeRealtimeMeasurements.retain(jdbc, mapper, "building", id, normalized);
        return Map.of("batchId", batchId, "inserted", pending.size(), "updated", updates.size(), "duplicates", duplicates);
    }

    private List<Map<String, Object>> measurements(long id, Long start, Long end, int limit) {
        return jdbc.query("SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<?"
                        + " ORDER BY timestamp_ms LIMIT ?", (rs, n) -> decode(rs.getString(1)),
                id, start == null ? Long.MIN_VALUE : start, end == null ? Long.MAX_VALUE : end, limit);
    }
    public Map<String,Object> measurementPage(long id,String from,String to,int page,int size){
        Map<String,Object> building=get(id,false);ZoneId zone=ZoneId.of(building.get("timezone").toString());
        Long start=from==null||from.isEmpty()?null:contract.timestamp(from,zone).toEpochMilli(),end=to==null||to.isEmpty()?null:contract.timestamp(to,zone).toEpochMilli();
        long startMs=start==null?Long.MIN_VALUE:start,endMs=end==null?Long.MAX_VALUE:end;
        long count=jdbc.queryForObject("SELECT COUNT(*) FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<?",Long.class,id,startMs,endMs);
        boolean truncated=count>200000;if(truncated&&(start!=null||end!=null))throw new IllegalArgumentException("所选区间超过 200000 条，请缩小范围");
        long visibleCount=truncated?200000:count;int pageSize=Math.max(1,Math.min(100,size)),pages=(int)Math.max(1,(visibleCount+pageSize-1)/pageSize);
        int current=Math.max(1,Math.min(page,pages));long offset=(long)(current-1)*pageSize;
        String sql=truncated
                ? "SELECT payload FROM (SELECT payload,timestamp_ms FROM building_measurement WHERE building_id=? ORDER BY timestamp_ms DESC LIMIT 200000) latest ORDER BY timestamp_ms LIMIT ? OFFSET ?"
                : "SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT ? OFFSET ?";
        List<Map<String,Object>> samples=truncated
                ? jdbc.query(sql,(rs,n)->decode(rs.getString(1)),id,pageSize,offset)
                : jdbc.query(sql,(rs,n)->decode(rs.getString(1)),id,startMs,endMs,pageSize,offset);
        Map<String,Object> result=new LinkedHashMap<>();result.put("samples",withCommunityMeasurements(id,samples));result.put("count",count);result.put("displayCount",visibleCount);
        result.put("page",current);result.put("size",pageSize);result.put("pages",pages);result.put("truncated",truncated);return result;
    }
    public Map<String, Object> detail(long id, String from, String to) {
        return detail(id,from,to,1,100);
    }
    public Map<String, Object> detail(long id, String from, String to,int page,int size) {
        Map<String, Object> building = get(id, false);
        ZoneId zone = ZoneId.of(building.get("timezone").toString());
        Long start = from == null || from.isEmpty() ? null : contract.timestamp(from, zone).toEpochMilli();
        Long end = to == null || to.isEmpty() ? null : contract.timestamp(to, zone).toEpochMilli();
        long total = jdbc.queryForObject("SELECT COUNT(*) FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<?",
                Long.class, id, start == null ? Long.MIN_VALUE : start, end == null ? Long.MAX_VALUE : end);
        boolean truncated = total > 200000;
        if (truncated && (start != null || end != null))
            throw new IllegalArgumentException("所选区间超过 200000 条，请缩小时间范围");
        List<Map<String, Object>> rows = truncated
                ? jdbc.query("SELECT payload FROM (SELECT payload,timestamp_ms FROM building_measurement"
                        + " WHERE building_id=? ORDER BY timestamp_ms DESC LIMIT 200000) latest ORDER BY timestamp_ms",
                    (rs, n) -> decode(rs.getString(1)), id)
                : measurements(id, start, end, 200001);
        rows=withCommunityMeasurements(id,rows);
        int interval = ((Number) building.get("intervalSeconds")).intValue();
        Map<String, Integer> missing = new LinkedHashMap<>();
        for (String key : MeasurementContract.FIELDS.keySet())
            missing.put(key, (int) rows.stream().filter(row -> !row.containsKey(key)).count());
        long gaps = 0;
        for (int i = 1; i < rows.size(); i++) {
            long a = Instant.parse(rows.get(i - 1).get("timestamp").toString()).getEpochSecond();
            long b = Instant.parse(rows.get(i).get("timestamp").toString()).getEpochSecond();
            gaps += Math.max(0, (b - a) / interval - 1);
        }
        boolean ready = false; String blocker = "";
        try {
            List<Map<String,Object>> hours=contract.hourly(rows, zone, interval);
            if(BuildingDatasetExporter.summary(building,hours).stream().anyMatch(f->"missing".equals(f.get("status"))))
                throw new IllegalArgumentException("发布字段缺失；约定时间轴需提供源日历标签");
            ready = !truncated;
        }
        catch (IllegalArgumentException e) { blocker = e.getMessage(); }
        if (truncated) blocker = "仅检查最近 200000 条；选择时间范围检查全部目标数据";
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("building", building); result.put("count", total); result.put("observedCount", rows.size());
        result.put("truncated", truncated); result.put("gaps", gaps);
        result.put("missing", missing); result.put("ready", ready); result.put("blocker", blocker);
        result.put("first", rows.isEmpty() ? null : rows.get(0).get("timestamp"));
        result.put("last", rows.isEmpty() ? null : rows.get(rows.size() - 1).get("timestamp"));
        int pageSize=Math.max(1,Math.min(100,size));long displayCount=truncated?200000:total;
        int pages=(int)Math.max(1,(displayCount+pageSize-1)/pageSize),currentPage=Math.max(1,Math.min(page,pages));
        List<Map<String,Object>> samplePage=truncated
                ? jdbc.query("SELECT payload FROM (SELECT payload,timestamp_ms FROM building_measurement WHERE building_id=? ORDER BY timestamp_ms DESC LIMIT 200000) latest ORDER BY timestamp_ms LIMIT ? OFFSET ?",(rs,n)->decode(rs.getString(1)),id,pageSize,(long)(currentPage-1)*pageSize)
                : jdbc.query("SELECT payload FROM building_measurement WHERE building_id=? AND timestamp_ms>=? AND timestamp_ms<? ORDER BY timestamp_ms LIMIT ? OFFSET ?",(rs,n)->decode(rs.getString(1)),id,start==null?Long.MIN_VALUE:start,end==null?Long.MAX_VALUE:end,pageSize,(long)(currentPage-1)*pageSize);
        result.put("samples",withCommunityMeasurements(id,samplePage));result.put("page",currentPage);result.put("size",pageSize);result.put("pages",pages);result.put("displayCount",displayCount);
        result.put("versions", jdbc.queryForList("SELECT v.id,v.schema_key AS schemaKey,v.name,v.purpose,v.start_time AS startTime,"
                + "v.end_time AS endTime,v.time_steps AS timeSteps,v.content_hash AS contentHash,v.create_time AS createTime"
                + " FROM building_dataset_version v JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY v.schema_key AND d.enabled=1 WHERE v.building_id=? ORDER BY v.create_time DESC", id));
        result.put("batches", jdbc.queryForList("SELECT id,source,accepted,duplicates,payload_hash AS payloadHash,"
                + "create_time AS createTime FROM building_ingestion_batch WHERE building_id=? ORDER BY create_time DESC LIMIT 30", id));
        return result;
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> publish(long id, Map<String, Object> request) throws Exception {
        Map<String, Object> building = get(id, true);
        ZoneId zone = ZoneId.of(building.get("timezone").toString());
        String name = text(request.get("name"));
        String purpose = text(request.get("purpose"));
        if (name.isEmpty() || name.length() > 160 || !List.of("train", "validation", "evaluation").contains(purpose))
            throw new IllegalArgumentException("请填写版本名称并选择用途");
        long start = contract.timestamp(request.get("from"), zone).toEpochMilli();
        long end = contract.timestamp(request.get("to"), zone).toEpochMilli();
        List<Map<String,Object>> hourly=publicationRows(id,building,request);
        Map<String,Object> preview=publicationSummary(building,hourly,request.get("simulation"));
        if(!Boolean.TRUE.equals(preview.get("ready"))) throw new IllegalArgumentException(preview.get("blocker").toString());
        String version = UUID.randomUUID().toString();
        String schemaKey = "building_" + id + "_" + version.replace("-", "");
        Path root = Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize();
        Path dir = root.resolve("datasets").resolve(schemaKey);
        Files.createDirectories(dir.getParent()); Files.createDirectory(dir);
        DatasetSnapshotFiles.cleanupOnRollback(dir);
        String contentHash = new BuildingDatasetExporter(mapper).write(dir, building, hourly, version,request.get("simulation"));
        String relative = root.relativize(dir).toString().replace('\\', '/');
        jdbc.update("INSERT INTO building_dataset_version(id,building_id,schema_key,name,purpose,start_time,end_time,time_steps,relative_path,content_hash)"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?)", version, id, schemaKey, name, purpose,
                Instant.ofEpochMilli(start).toString(), Instant.ofEpochMilli(end).toString(), hourly.size(), relative, contentHash);
        jdbc.update("INSERT INTO citylearn_dataset(schema_key,display_name,relative_path,building_count,time_steps,chesca_compatible,enabled,sort_order,description)"
                + " VALUES (?,?,?,1,?,0,1,200,?)", schemaKey, name, relative, hourly.size(),
                "建筑外部数据 · "+preview.get("simulation")+" · " + version);
        return Map.of("id", version, "schemaKey", schemaKey, "timeSteps", hourly.size(), "contentHash", contentHash);
    }

    public Map<String,Object> preview(long id,Map<String,Object> request) {
        Map<String,Object> building=get(id,false);
        try {return publicationSummary(building,publicationRows(id,building,request),request.get("simulation"));}
        catch(IllegalArgumentException error) {return Map.of("ready",false,"blocker",error.getMessage(),"fields",List.of());}
    }
    @SuppressWarnings("unchecked")
    private Map<String,Object> publicationSummary(Map<String,Object> building,List<Map<String,Object>> rows,Object options) {
        Map<String,Object> devices=building.containsKey("devices")?(Map<String,Object>)building.get("devices"):
                Map.of("electrical_storage",Map.of(),"cooling_device",Map.of(),"heating_device",Map.of(),"dhw_device",Map.of());
        BuildingExportOptions simulation=BuildingExportOptions.parse(options,devices);
        List<Map<String,Object>> fields=BuildingDatasetExporter.summary(building,rows);
        String blocker=fields.stream().filter(field->"missing".equals(field.get("status"))).map(field->field.get("label").toString()).collect(Collectors.joining("、"));
        for(String demand:List.of("cooling","heating","dhw")) if(!devices.containsKey(demand+"_device") && rows.stream().anyMatch(row->((Number)row.get(demand+"_demand")).doubleValue()>0)) blocker+=" 缺少设备: "+demand+"_device";
        return Map.of("ready",blocker.isEmpty(),"blocker",blocker.isEmpty()?"":"发布条件不满足: "+blocker,
                "fields",fields,"simulation",simulation.asMap(),"timeSteps",rows.size(),"timestampKind",building.getOrDefault("timestampKind","measured"));
    }
    private List<Map<String,Object>> publicationRows(long id,Map<String,Object> building,Map<String,Object> request) {
        ZoneId zone=ZoneId.of(building.get("timezone").toString());
        long start=contract.timestamp(request.get("from"),zone).toEpochMilli(),end=contract.timestamp(request.get("to"),zone).toEpochMilli();
        int interval = ((Number) building.get("intervalSeconds")).intValue();
        if (end <= start || (end - start) % (interval * 1000L) != 0) throw new IllegalArgumentException("时间区间无效（结束时间不包含在内）");
        long expected = (end - start) / (interval * 1000L);
        if (expected > 200000) throw new IllegalArgumentException("单个版本最多 200000 条源数据");
        List<Map<String, Object>> raw = withCommunityMeasurements(id,measurements(id, start, end, 200001));
        if (raw.size() != expected || raw.isEmpty() || !raw.get(0).get("timestamp").equals(Instant.ofEpochMilli(start).toString()))
            throw new IllegalArgumentException("所选区间边界或内部有缺失，不能发布");
        return contract.hourly(raw, zone, interval);
    }

    public Path versionDirectory(long buildingId, String version) {
        get(buildingId, false);
        List<String> paths = jdbc.query("SELECT v.relative_path FROM building_dataset_version v JOIN citylearn_dataset d ON BINARY d.schema_key=BINARY v.schema_key AND d.enabled=1 WHERE v.id=? AND v.building_id=?",
                (rs, n) -> rs.getString(1), version, buildingId);
        if (paths.isEmpty()) throw new IllegalArgumentException("数据版本不存在");
        Path root = Paths.get(files.getPythonFilePath()).toAbsolutePath().normalize();
        Path path = root.resolve(paths.get(0)).normalize();
        if (!path.startsWith(root.resolve("datasets"))) throw new IllegalArgumentException("无效数据集路径");
        return path;
    }
    private List<Map<String,Object>> withCommunityMeasurements(long id,List<Map<String,Object>> local) {
        Long owner=communityId(id);if(owner==null || local.isEmpty())return local;
        long start=Instant.parse(local.get(0).get("timestamp").toString()).toEpochMilli(),end=Instant.parse(local.get(local.size()-1).get("timestamp").toString()).toEpochMilli();
        Map<String,Map<String,Object>> shared=new HashMap<>();
        for(Map<String,Object> row:jdbc.query("SELECT payload FROM community_measurement WHERE community_id=? AND timestamp_ms>=? AND timestamp_ms<=? ORDER BY timestamp_ms",(rs,n)->decode(rs.getString(1)),owner,start,end))shared.put(row.get("timestamp").toString(),row);
        List<Map<String,Object>> result=new ArrayList<>();
        for(Map<String,Object> original:local) {
            Map<String,Object> row=new LinkedHashMap<>(original),common=shared.get(original.get("timestamp"));
            if(common!=null) for(Map.Entry<String,Object> field:common.entrySet()) {
                Object previous=row.get(field.getKey());
                if(previous!=null && !(previous instanceof Number && field.getValue() instanceof Number
                        ? Math.abs(((Number)previous).doubleValue()-((Number)field.getValue()).doubleValue())<=1e-12*Math.max(1,Math.max(Math.abs(((Number)previous).doubleValue()),Math.abs(((Number)field.getValue()).doubleValue())))
                        : previous.equals(field.getValue())))throw new IllegalArgumentException("建筑与社区共享数据冲突: "+field.getKey()+" @ "+row.get("timestamp"));
                row.putIfAbsent(field.getKey(),field.getValue());
            }
            result.add(row);
        }
        return result;
    }
    private String text(Object value) { return value == null ? "" : value.toString().trim(); }
    private String hash(String value) { return BuildingDatasetExporter.sha256(value.getBytes(StandardCharsets.UTF_8)); }
    private String encode(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (Exception e) { throw new IllegalArgumentException("数据序列化失败", e); }
    }
    private Map<String, Object> decode(String value) {
        try { return mapper.readValue(value, new TypeReference<LinkedHashMap<String, Object>>() {}); }
        catch (Exception e) { throw new IllegalArgumentException("数据读取失败", e); }
    }
}

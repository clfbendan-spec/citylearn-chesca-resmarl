package com.citylearn.building;

import com.citylearn.common.Result;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import javax.annotation.Resource;

/** Device endpoint uses a building-scoped bearer token; browser session is deliberately irrelevant. */
@RestController
@RequestMapping("/ingest/v1/buildings")
public class BuildingRealtimeController {
    @Resource private BuildingIngestionService service;
    @PostMapping("/{id}/measurements")
    public ResponseEntity<?> ingest(@PathVariable long id,
                                    @RequestHeader(value = "Authorization", required = false) String token,
                                    @RequestBody BuildingController.IngestionRequest request) {
        if (!service.authenticate(id, token))
            return ResponseEntity.status(401).body(Result.fail("无效的建筑接入令牌"));
        return ResponseEntity.ok(Result.success(service.ingest(id, request.getRows(),
                request.getMapping(), request.getUnits(), "realtime")));
    }
}

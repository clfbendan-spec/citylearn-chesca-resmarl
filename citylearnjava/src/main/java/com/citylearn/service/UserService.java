package com.citylearn.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.StringUtils;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.citylearn.common.PageBean;
import com.citylearn.common.PasswordHasher;
import com.citylearn.common.SessionKeys;
import com.citylearn.common.UserRoles;
import com.citylearn.config.SystemConfig;
import com.citylearn.dao.PermissionMapper;
import com.citylearn.dao.UserMapper;
import com.citylearn.dao.UserPermissionMapper;
import com.citylearn.entity.Permission;
import com.citylearn.entity.User;
import com.citylearn.entity.UserPermission;
import com.citylearn.vo.UserVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.CollectionUtils;

import javax.annotation.Resource;
import javax.servlet.http.HttpSession;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 用户与登录、权限
 */
@Service
public class UserService implements SystemConfig {

    @Resource
    private UserMapper userMapper;

    @Resource
    private PermissionMapper permissionMapper;

    @Resource
    private UserPermissionMapper userPermissionMapper;

    @Resource
    private PasswordHasher passwordHasher;

    public UserVO login(String username, String password, HttpSession session) {
        if (StringUtils.isBlank(username) || StringUtils.isBlank(password)) {
            throw new IllegalArgumentException("用户名和密码不能为空");
        }
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, username.trim())
                .eq(User::getIfDelete, false)
                .last("LIMIT 1");
        User user = userMapper.selectOne(wrapper);
        if (user == null || !passwordHasher.matches(password, user.getPassword())) {
            throw new IllegalArgumentException("用户名或密码错误");
        }
        upgradeLegacyPassword(user, password);
        UserVO vo = toVO(user);
        session.setAttribute(SessionKeys.LOGIN_USER, vo);
        writeSessionPermissions(user, session);
        return vo;
    }

    /**
     * 历史遗留的明文密码：登录成功后顺手改写成 bcrypt 哈希（不改变用户的密码本身）。
     *
     * <p>这样不用停机、也不用让任何人改密码，账号会在「下一次登录时」各自完成升级；
     * 全部账号登录过一遍后，库里就不再有明文。写库失败不影响登录，只记日志下次再试。
     */
    private void upgradeLegacyPassword(User user, String rawPassword) {
        if (passwordHasher.isHashed(user.getPassword())) {
            return;
        }
        try {
            String hashed = passwordHasher.encode(rawPassword);
            user.setPassword(hashed);
            user.setUpdateTime(new Date());
            userMapper.updateById(user);
        } catch (Exception e) {
            System.err.println("[密码迁移] 用户 " + user.getUsername() + " 明文密码升级失败：" + e.getMessage());
        }
    }

    /**
     * 把用户的权限码集合写入 session（登录时调用；接口鉴权读的就是这份）。
     *
     * <p>SUPER_ADMIN 拿到的是「全部启用权限码」，即默认拥有全部权限；
     * {@code PermissionInterceptor} 另有角色直通兜底，即使这里漏写也不会把超管锁在外面。
     *
     * <p>权限码集合在登录时写入；{@code currentUser} 每次刷新用户信息时也会重新写入，
     * 所以管理员改完权限后对方刷新页面即可生效（不必重新登录）。
     */
    public void writeSessionPermissions(User user, HttpSession session) {
        if (user == null || session == null) {
            return;
        }
        Set<String> codes = new LinkedHashSet<>(listUserPermissionCodes(user.getId()));
        session.setAttribute(SessionKeys.LOGIN_PERMS, codes);
    }

    public void logout(HttpSession session) {
        if (session != null) {
            session.removeAttribute(SessionKeys.LOGIN_USER);
            session.invalidate();
        }
    }

    public UserVO currentUser(HttpSession session) {
        if (session == null) {
            return null;
        }
        Object attr = session.getAttribute(SessionKeys.LOGIN_USER);
        if (!(attr instanceof UserVO)) {
            return null;
        }
        UserVO cached = (UserVO) attr;
        User user = userMapper.selectById(cached.getId());
        if (user == null || Boolean.TRUE.equals(user.getIfDelete())) {
            session.removeAttribute(SessionKeys.LOGIN_USER);
            return null;
        }
        UserVO fresh = toVO(user);
        session.setAttribute(SessionKeys.LOGIN_USER, fresh);
        // 顺带刷新权限集合：管理员改完权限后，用户刷新页面（会请求 /web/auth/current）即可生效，
        // 不必等到重新登录
        writeSessionPermissions(user, session);
        return fresh;
    }

    public PageBean<UserVO> listPageUsers(String username, Integer currentPage, Integer pageSize) {
        int pageNum = currentPage == null || currentPage < 1 ? 1 : currentPage;
        int size = pageSize == null || pageSize < 1 ? 10 : pageSize;
        Page<User> page = new Page<>(pageNum, size);
        PageBean<UserVO> pageBean = new PageBean<>();
        pageBean.setRows(new ArrayList<>());
        pageBean.setTotal(0);

        LambdaQueryWrapper<User> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(User::getIfDelete, false);
        queryWrapper.like(StringUtils.isNotBlank(username), User::getUsername, username);
        queryWrapper.orderByAsc(User::getCreateTime);
        List<User> infos = userMapper.selectPage(page, queryWrapper).getRecords();
        if (CollectionUtils.isEmpty(infos)) {
            return pageBean;
        }
        List<UserVO> rows = infos.stream().map(this::toVO).collect(Collectors.toList());
        pageBean.setRows(rows);
        pageBean.setTotal((int) page.getTotal());
        return pageBean;
    }

    public void addAdmin(String username, String password, String nickname) {
        if (StringUtils.isBlank(username) || StringUtils.isBlank(password)) {
            throw new IllegalArgumentException("用户名和密码不能为空");
        }
        String name = username.trim();
        if (existsUsername(name, null)) {
            throw new IllegalArgumentException("用户名已存在");
        }
        User user = new User();
        user.setId(getUUID());
        user.setUsername(name);
        // 只存 bcrypt 哈希，明文不落库、不写日志
        user.setPassword(passwordHasher.encode(password));
        user.setNickname(StringUtils.isBlank(nickname) ? name : nickname.trim());
        user.setRole(UserRoles.ADMIN);
        user.setIfDelete(false);
        Date now = new Date();
        user.setCreateTime(now);
        user.setUpdateTime(now);
        userMapper.insert(user);
    }

    /**
     * 编辑系统管理员：只改用户名与显示名称，**不改密码**。
     *
     * <p>密码统一走 {@link #resetPassword(String, String)}（前端「重置密码」按钮），
     * 这样「编辑」是一个不会撤销凭证信息的低风险操作，也避免两个入口给出不同的密码规则。
     * 需要改密码时调用 resetPassword，本方法不再接受 password 参数。
     */
    public void editAdmin(String id, String username, String nickname) {
        if (StringUtils.isBlank(id)) {
            throw new IllegalArgumentException("用户 ID 不能为空");
        }
        User user = userMapper.selectById(id);
        if (user == null || Boolean.TRUE.equals(user.getIfDelete())) {
            throw new IllegalArgumentException("用户不存在");
        }
        if (UserRoles.SUPER_ADMIN.equals(user.getRole())) {
            throw new IllegalArgumentException("不能编辑超级管理员账号（请仅管理普通系统管理员）");
        }
        if (StringUtils.isNotBlank(username)) {
            String name = username.trim();
            if (existsUsername(name, id)) {
                throw new IllegalArgumentException("用户名已存在");
            }
            user.setUsername(name);
        }
        if (nickname != null) {
            user.setNickname(nickname.trim());
        }
        user.setUpdateTime(new Date());
        userMapper.updateById(user);
    }

    @Transactional(rollbackFor = Exception.class)
    public void deleteAdmin(String id) {
        if (StringUtils.isBlank(id)) {
            throw new IllegalArgumentException("用户 ID 不能为空");
        }
        User user = userMapper.selectById(id);
        if (user == null || Boolean.TRUE.equals(user.getIfDelete())) {
            throw new IllegalArgumentException("用户不存在");
        }
        if (UserRoles.SUPER_ADMIN.equals(user.getRole())) {
            throw new IllegalArgumentException("不能删除超级管理员");
        }
        user.setIfDelete(true);
        user.setUpdateTime(new Date());
        userMapper.updateById(user);
        clearUserPermissions(id);
    }

    public void resetPassword(String id, String newPassword) {
        if (StringUtils.isBlank(id)) {
            throw new IllegalArgumentException("用户 ID 不能为空");
        }
        if (StringUtils.isBlank(newPassword)) {
            throw new IllegalArgumentException("新密码不能为空");
        }
        User user = userMapper.selectById(id);
        if (user == null || Boolean.TRUE.equals(user.getIfDelete())) {
            throw new IllegalArgumentException("用户不存在");
        }
        user.setPassword(passwordHasher.encode(newPassword));
        user.setUpdateTime(new Date());
        userMapper.updateById(user);
    }

    /**
     * 从 permission 表构建可分配权限树
     */
    public List<Map<String, Object>> permissionTree() {
        List<Permission> list = listEnabledPermissions();
        Map<String, Map<String, Object>> nodeMap = new LinkedHashMap<>();
        for (Permission p : list) {
            Map<String, Object> node = new LinkedHashMap<>();
            node.put("code", p.getCode());
            node.put("label", p.getName());
            node.put("children", new ArrayList<Map<String, Object>>());
            nodeMap.put(p.getCode(), node);
        }
        List<Map<String, Object>> roots = new ArrayList<>();
        for (Permission p : list) {
            Map<String, Object> node = nodeMap.get(p.getCode());
            String parent = p.getParentCode();
            if (StringUtils.isNotBlank(parent) && nodeMap.containsKey(parent)) {
                @SuppressWarnings("unchecked")
                List<Map<String, Object>> children = (List<Map<String, Object>>) nodeMap.get(parent).get("children");
                children.add(node);
            } else {
                roots.add(node);
            }
        }
        // 无子节点时去掉空 children，前端树更干净
        stripEmptyChildren(roots);
        return roots;
    }

    public List<String> listUserPermissionCodes(String userId) {
        if (StringUtils.isBlank(userId)) {
            return new ArrayList<>();
        }
        User user = userMapper.selectById(userId);
        if (user == null || Boolean.TRUE.equals(user.getIfDelete())) {
            throw new IllegalArgumentException("用户不存在");
        }
        if (UserRoles.SUPER_ADMIN.equals(user.getRole())) {
            return listEnabledPermissions().stream().map(Permission::getCode).collect(Collectors.toList());
        }
        List<String> codes = userPermissionMapper.selectPermissionCodesByUserId(userId);
        return codes == null ? new ArrayList<>() : codes;
    }

    @Transactional(rollbackFor = Exception.class)
    public void savePermissions(String id, List<String> permissions) {
        if (StringUtils.isBlank(id)) {
            throw new IllegalArgumentException("用户 ID 不能为空");
        }
        User user = userMapper.selectById(id);
        if (user == null || Boolean.TRUE.equals(user.getIfDelete())) {
            throw new IllegalArgumentException("用户不存在");
        }
        if (UserRoles.SUPER_ADMIN.equals(user.getRole())) {
            throw new IllegalArgumentException("超级管理员拥有全部权限，无需分配");
        }
        List<Permission> all = listEnabledPermissions();
        Map<String, Permission> byCode = all.stream()
                .collect(Collectors.toMap(Permission::getCode, p -> p, (a, b) -> a, LinkedHashMap::new));
        List<String> normalized = normalizePermissions(permissions, byCode);
        clearUserPermissions(id);
        Date now = new Date();
        for (String code : normalized) {
            Permission perm = byCode.get(code);
            if (perm == null) {
                continue;
            }
            UserPermission rel = new UserPermission();
            rel.setId(getUUID());
            rel.setUserId(id);
            rel.setPermissionId(perm.getId());
            rel.setCreateTime(now);
            userPermissionMapper.insert(rel);
        }
        user.setUpdateTime(now);
        userMapper.updateById(user);
    }

    public void requireSuperAdmin(HttpSession session) {
        UserVO current = currentUser(session);
        if (current == null) {
            throw new IllegalStateException("未登录");
        }
        if (!UserRoles.SUPER_ADMIN.equals(current.getRole())) {
            throw new IllegalStateException("无权限：仅超级管理员可进行用户管理");
        }
    }

    private List<Permission> listEnabledPermissions() {
        LambdaQueryWrapper<Permission> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Permission::getEnabled, true);
        wrapper.orderByAsc(Permission::getSortOrder).orderByAsc(Permission::getCode);
        return permissionMapper.selectList(wrapper);
    }

    private void clearUserPermissions(String userId) {
        LambdaQueryWrapper<UserPermission> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(UserPermission::getUserId, userId);
        userPermissionMapper.delete(wrapper);
    }

    private List<String> normalizePermissions(List<String> permissions, Map<String, Permission> byCode) {
        LinkedHashSet<String> result = new LinkedHashSet<>();
        if (permissions != null) {
            for (String code : permissions) {
                if (StringUtils.isNotBlank(code) && byCode.containsKey(code.trim())) {
                    result.add(code.trim());
                }
            }
        }
        // 勾选子权限时自动带上全部上级（菜单 / 分组节点），否则「只勾了子权限」的用户连入口都没有。
        // 上限 10 层只是防御脏数据里的环（parent_code 指回自己）。
        for (String code : new ArrayList<>(result)) {
            Permission node = byCode.get(code);
            int guard = 0;
            while (node != null && StringUtils.isNotBlank(node.getParentCode()) && guard++ < 10) {
                String parent = node.getParentCode();
                if (!byCode.containsKey(parent)) {
                    break;
                }
                result.add(parent);
                node = byCode.get(parent);
            }
        }
        List<String> ordered = new ArrayList<>();
        for (Permission p : listEnabledPermissions()) {
            if (result.contains(p.getCode())) {
                ordered.add(p.getCode());
            }
        }
        return ordered;
    }

    private void stripEmptyChildren(List<Map<String, Object>> nodes) {
        if (nodes == null) {
            return;
        }
        for (Map<String, Object> node : nodes) {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> children = (List<Map<String, Object>>) node.get("children");
            if (children == null || children.isEmpty()) {
                node.remove("children");
            } else {
                stripEmptyChildren(children);
            }
        }
    }

    private boolean existsUsername(String username, String excludeId) {
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, username)
                .eq(User::getIfDelete, false);
        if (StringUtils.isNotBlank(excludeId)) {
            wrapper.ne(User::getId, excludeId);
        }
        return userMapper.selectCount(wrapper) > 0;
    }

    private UserVO toVO(User user) {
        UserVO vo = new UserVO();
        BeanUtils.copyProperties(user, vo);
        if (UserRoles.SUPER_ADMIN.equals(user.getRole())) {
            vo.setPermissions(listEnabledPermissions().stream()
                    .map(Permission::getCode)
                    .collect(Collectors.toList()));
        } else {
            List<String> codes = userPermissionMapper.selectPermissionCodesByUserId(user.getId());
            vo.setPermissions(codes == null ? new ArrayList<>() : new ArrayList<>(codes));
        }
        return vo;
    }
}

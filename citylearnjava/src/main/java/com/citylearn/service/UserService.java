package com.citylearn.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.StringUtils;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.citylearn.common.PageBean;
import com.citylearn.common.PermissionCodes;
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

    public UserVO login(String username, String password, HttpSession session) {
        if (StringUtils.isBlank(username) || StringUtils.isBlank(password)) {
            throw new IllegalArgumentException("用户名和密码不能为空");
        }
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(User::getUsername, username.trim())
                .eq(User::getIfDelete, false)
                .last("LIMIT 1");
        User user = userMapper.selectOne(wrapper);
        if (user == null || !password.equals(user.getPassword())) {
            throw new IllegalArgumentException("用户名或密码错误");
        }
        UserVO vo = toVO(user);
        session.setAttribute(SessionKeys.LOGIN_USER, vo);
        return vo;
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
        user.setPassword(password);
        user.setNickname(StringUtils.isBlank(nickname) ? name : nickname.trim());
        user.setRole(UserRoles.ADMIN);
        user.setIfDelete(false);
        Date now = new Date();
        user.setCreateTime(now);
        user.setUpdateTime(now);
        userMapper.insert(user);
    }

    public void editAdmin(String id, String username, String password, String nickname) {
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
        if (StringUtils.isNotBlank(password)) {
            user.setPassword(password);
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
        user.setPassword(newPassword);
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
        List<String> normalized = normalizePermissions(permissions, byCode.keySet());
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

    private List<String> normalizePermissions(List<String> permissions, Set<String> allowed) {
        LinkedHashSet<String> result = new LinkedHashSet<>();
        if (permissions != null) {
            for (String code : permissions) {
                if (StringUtils.isNotBlank(code) && allowed.contains(code.trim())) {
                    result.add(code.trim());
                }
            }
        }
        // 子权限勾选时自动带上对应菜单
        if (result.contains(PermissionCodes.CODE_EDITOR_OPERATE) || result.contains(PermissionCodes.CODE_EDITOR_DELETE)) {
            if (allowed.contains(PermissionCodes.MENU_CODE_EDITOR)) {
                result.add(PermissionCodes.MENU_CODE_EDITOR);
            }
        }
        if (result.contains(PermissionCodes.RES_MARL_OPERATE)) {
            if (allowed.contains(PermissionCodes.MENU_RES_MARL)) {
                result.add(PermissionCodes.MENU_RES_MARL);
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

-- 权限已迁移至 permission + user_permission 表，可删除 user.permissions 冗余列
-- 若列不存在可忽略报错
ALTER TABLE `user` DROP COLUMN `permissions`;

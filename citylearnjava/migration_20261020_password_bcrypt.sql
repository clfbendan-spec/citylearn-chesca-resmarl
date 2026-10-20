-- ============================================================================
-- 密码明文 → bcrypt 哈希（2026-10-20）
--
-- 背景：`user.password` 原本直接存明文（admin/admin2 都是 '000000'），
--       登录时用 password.equals() 明文比对。现改为 bcrypt(cost=10) + 每用户随机盐，
--       存储格式 `{bcrypt}$2a$10$...`（68 字符，表字段 varchar(128) 够用）。
--
-- 本脚本只把**仍是明文**的行改写为哈希：
--   条件里带 `password = '000000'` ⇒ 重复执行是幂等的（已迁移的行不会被再次改动，
--   否则重跑会把用户自己改过的密码覆盖回 000000）。
--
-- 两行都是同一个明文口令 000000，但**盐不同 ⇒ 哈希串不同**，这是 bcrypt 的正常表现。
-- 迁移后登录口令不变，两个账号仍是 000000（可用「重置密码」改成更强的口令）。
--
-- 回滚：`user_table_backup_20261020.sql`（含 DROP TABLE + 完整数据，可直接恢复）。
-- 代码侧的兼容：UserService.login 对「无 {bcrypt} 前缀」的裸串仍走明文比对，
--   并在登录成功后自动升级为哈希 ⇒ 即使漏迁移某个账号也不会被锁在门外。
-- ============================================================================

UPDATE `user`
   SET `password` = '{bcrypt}$2a$10$hPyWJFln/aq3.vlCq2/LfOgMeJqZrPQ/jjwtmRFfOpixwXogdh8b.',
       `update_time` = NOW()
 WHERE `id` = '1'
   AND `password` = '000000';

UPDATE `user`
   SET `password` = '{bcrypt}$2a$10$NSdWxJgsWEgBvc7ArXk67u/KAb.F05EMoxNmd1OMqCrKaRte.Qz.O',
       `update_time` = NOW()
 WHERE `id` = '99526c7d39ae4f80a18523374b057f71'
   AND `password` = '000000';

-- 校验：应为 2 行、均为 {bcrypt} 前缀、长度 68、且不再有 6 位明文
SELECT `username`,
       LEFT(`password`, 8) AS prefix,
       CHAR_LENGTH(`password`) AS len,
       (`password` LIKE '{bcrypt}%') AS is_hashed
  FROM `user`
 ORDER BY `id`;

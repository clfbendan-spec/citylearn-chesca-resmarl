<template>
  <div class="login-page">
    <div class="login-panel">
      <div class="login-brand">建筑群节能控制</div>
      <p class="login-sub">请登录后继续使用系统</p>
      <el-form ref="form" :model="form" :rules="rules" label-position="top" @submit.native.prevent="handleLogin">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" prefix-icon="el-icon-user" clearable @keyup.enter.native="handleLogin" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="el-icon-lock"
            show-password
            clearable
            @keyup.enter.native="handleLogin"
          />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" native-type="submit" @click="handleLogin">
          登录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script>
import { login } from '../api/auth'

export default {
  name: 'LoginPage',
  data() {
    return {
      loading: false,
      form: {
        username: '',
        password: ''
      },
      rules: {
        username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
        password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
      }
    }
  },
  methods: {
    handleLogin() {
      this.$refs.form.validate(async (valid) => {
        if (!valid) return
        this.loading = true
        try {
          const { ok, data, message } = await login(this.form.username.trim(), this.form.password)
          if (ok) {
            this.$message.success('登录成功')
            this.$emit('login-success', data)
          } else {
            this.$message.error(message || '登录失败')
          }
        } finally {
          this.loading = false
        }
      })
    }
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--primary-background-color);
}

.login-panel {
  width: 100%;
  max-width: 400px;
  padding: 36px 32px 40px;
  background: var(--card-background-color, #fff);
  border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.08));
  border-radius: var(--ha-card-border-radius);
  box-shadow: var(--ha-card-box-shadow);
}

.login-brand {
  font-size: 22px;
  font-weight: 600;
  color: var(--primary-text-color, #212121);
  letter-spacing: 0;
}

.login-sub {
  margin: 8px 0 28px;
  font-size: 13px;
  color: var(--secondary-text-color, #727272);
}

.login-btn {
  width: 100%;
  margin-top: 8px;
}

.login-page ::v-deep .el-form-item__label {
  padding-bottom: 4px;
  line-height: 1.4;
  color: var(--secondary-text-color, #727272);
}
</style>

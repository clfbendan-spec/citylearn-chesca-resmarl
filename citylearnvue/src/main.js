import Vue from 'vue'
import ElementUI from 'element-ui';
import 'element-ui/lib/theme-chalk/index.css'
import 'remixicon/fonts/remixicon.css'
import './styles/ha-theme.css'
import axios from 'axios'
import VueAxios from 'vue-axios'
import App from './App.vue'

axios.defaults.withCredentials = true

axios.interceptors.response.use(
  (response) => {
    const body = response && response.data
    if (body && body.code === 401) {
      window.dispatchEvent(new CustomEvent('citylearn-auth-required'))
    }
    // 后端接口级鉴权：普通用户缺对应权限时返回 code=403（HTTP 仍是 200）。
    // 页面自己会把这类响应当成"加载失败"，这里额外给一次提示并做 3 秒节流，
    // 避免一个页面并发多个读接口时刷一屏警告。
    if (body && body.code === 403) {
      const now = Date.now()
      if (!window.__permWarnAt || now - window.__permWarnAt > 3000) {
        window.__permWarnAt = now
        window.dispatchEvent(new CustomEvent('citylearn-permission-denied', {
          detail: { message: body.message || '无权限访问该接口' }
        }))
      }
    }
    return response
  },
  (error) => Promise.reject(error)
)

Vue.use(ElementUI);
Vue.use(VueAxios, axios)
Vue.config.productionTip = false

new Vue({
  render: h => h(App),
}).$mount('#app')

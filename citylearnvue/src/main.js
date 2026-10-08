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
    if (response && response.data && response.data.code === 401) {
      window.dispatchEvent(new CustomEvent('citylearn-auth-required'))
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

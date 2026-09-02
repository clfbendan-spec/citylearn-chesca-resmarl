const { defineConfig } = require('@vue/cli-service')
const MonacoWebpackPlugin = require('monaco-editor-webpack-plugin')

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    proxy: {
      '/api': {
        target: 'http://localhost:8088', // 后端服务器的地址
        changeOrigin: true,
        pathRewrite: { '^/api': '' } // 重写路径，去掉 /api
      }
    }
  },
  configureWebpack: {
    plugins: [
      new MonacoWebpackPlugin({
        // 可选，按需配置语言
        languages: ['python', 'javascript', 'html', 'css', 'json']
      })
    ]
  },
  chainWebpack: config => {
    // 处理Monaco Editor的CSS文件
    config.module
      .rule('monaco')
      .test(/\.css$/)
      .include
      .add(/node_modules\/monaco-editor/)
      .end()
      .use('style-loader')
      .loader('style-loader')
      .end()
      .use('css-loader')
      .loader('css-loader')
      .end();
  }

})

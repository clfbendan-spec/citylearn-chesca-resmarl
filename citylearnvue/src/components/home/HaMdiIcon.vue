<template>
  <svg
    class="ha-mdi"
    viewBox="0 0 24 24"
    :width="size"
    :height="size"
    aria-hidden="true"
    focusable="false"
  >
    <path :d="path" fill="currentColor" />
  </svg>
</template>

<script>
import { MDI } from '@/utils/haIcons'

export default {
  name: 'HaMdiIcon',
  props: {
    name: { type: String, required: true },
    size: { type: [Number, String], default: 24 }
  },
  computed: {
    path() {
      return MDI[this.name] || MDI.weatherCloudy
    }
  }
}
</script>

<style scoped>
.ha-mdi {
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
}
</style>

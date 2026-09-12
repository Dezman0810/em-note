<script setup lang="ts">
import { RouterView } from 'vue-router'
import ForceChangePasswordModal from './components/ForceChangePasswordModal.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
</script>

<template>
  <RouterView />
  <ForceChangePasswordModal v-if="auth.user?.must_change_password" />
</template>

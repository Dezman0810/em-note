<script setup lang="ts">
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import { computed, ref } from 'vue'
import { decryptText, type EncryptedPayload } from '../../utils/cryptoSecret'

const props = defineProps(nodeViewProps)

const showPassOpen = ref(false)
const showResultOpen = ref(false)
const passInput = ref('')
const passErr = ref('')
const decrypted = ref('')
const busy = ref(false)

const payload = computed((): EncryptedPayload => ({
  version: Number(props.node.attrs.version) || 1,
  salt: String(props.node.attrs.salt ?? ''),
  iv: String(props.node.attrs.iv ?? ''),
  ciphertext: String(props.node.attrs.ciphertext ?? ''),
}))

function openPass() {
  passErr.value = ''
  passInput.value = ''
  showPassOpen.value = true
}

function closePass() {
  showPassOpen.value = false
}

async function submitPass() {
  const p = passInput.value
  if (!p) {
    passErr.value = 'Введите ключ'
    return
  }
  busy.value = true
  passErr.value = ''
  try {
    decrypted.value = await decryptText(payload.value, p)
    closePass()
    showResultOpen.value = true
  } catch {
    passErr.value = 'Неверный ключ или повреждённые данные'
  } finally {
    busy.value = false
  }
}

function closeResult() {
  showResultOpen.value = false
  decrypted.value = ''
}

async function copyDecrypted() {
  try {
    await navigator.clipboard.writeText(decrypted.value)
  } catch {
    passErr.value = 'Не удалось скопировать'
  }
}
</script>

<template>
  <NodeViewWrapper as="span" class="enc-inline-wrap" contenteditable="false">
    <span class="enc-inline" title="Зашифровано: нажмите «Показать» и введите ключ">
      <span class="enc-inline-ico" aria-hidden="true">🔒</span>
      <span class="enc-inline-lab">скрыто</span>
      <button type="button" class="enc-inline-btn" @click.stop.prevent="openPass">Показать</button>
    </span>

    <Teleport to="body">
      <div v-if="showPassOpen" class="enc-modal-root" @click.self="closePass">
        <div class="enc-modal" role="dialog" aria-label="Ключ для расшифровки">
          <h3 class="enc-modal-title">Введите ключ</h3>
          <p class="enc-modal-hint muted small">Ключ не сохраняется и не отправляется на сервер.</p>
          <input
            v-model="passInput"
            type="password"
            class="enc-modal-input"
            autocomplete="off"
            placeholder="Ключ / парольная фраза"
            @keydown.enter.prevent="submitPass"
          />
          <p v-if="passErr" class="enc-modal-err">{{ passErr }}</p>
          <div class="enc-modal-actions">
            <button type="button" class="enc-modal-cancel" @click="closePass">Отмена</button>
            <button type="button" class="enc-modal-ok" :disabled="busy" @click="submitPass">
              {{ busy ? '…' : 'Расшифровать' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showResultOpen" class="enc-modal-root" @click.self="closeResult">
        <div class="enc-modal enc-modal-wide" role="dialog" aria-label="Расшифрованный текст">
          <h3 class="enc-modal-title">Содержимое</h3>
          <textarea class="enc-modal-ta" readonly rows="6" :value="decrypted" />
          <div class="enc-modal-actions">
            <button type="button" class="enc-modal-cancel" @click="closeResult">Закрыть</button>
            <button type="button" class="enc-modal-ok" @click="copyDecrypted">Копировать</button>
          </div>
        </div>
      </div>
    </Teleport>
  </NodeViewWrapper>
</template>

<style scoped>
.enc-inline-wrap {
  vertical-align: baseline;
}
.enc-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  max-width: 100%;
  padding: 0.1rem 0.38rem 0.12rem;
  border-radius: 6px;
  border: 1px solid rgba(37, 99, 235, 0.35);
  background: rgba(37, 99, 235, 0.06);
  font-size: 0.78rem;
  line-height: 1.35;
  user-select: none;
  white-space: nowrap;
}
.enc-inline-ico {
  font-size: 0.75rem;
  line-height: 1;
  flex-shrink: 0;
}
.enc-inline-lab {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.enc-inline-btn {
  border: none;
  background: rgba(37, 99, 235, 0.15);
  color: var(--accent);
  font-size: 0.65rem;
  font-weight: 600;
  padding: 0.12rem 0.35rem;
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
}
.enc-inline-btn:hover {
  background: rgba(37, 99, 235, 0.25);
}
.enc-modal-root {
  position: fixed;
  inset: 0;
  z-index: 1100;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  box-sizing: border-box;
}
.enc-modal {
  width: min(380px, 100%);
  padding: 1rem 1.05rem;
  border-radius: var(--radius-lg, 14px);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow-panel, 0 8px 40px rgba(15, 23, 42, 0.15));
}
.enc-modal-wide {
  width: min(480px, 100%);
}
.enc-modal-title {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 650;
}
.enc-modal-hint {
  margin: 0 0 0.65rem;
}
.enc-modal-input,
.enc-modal-ta {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  font-size: 0.85rem;
  padding: 0.4rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  margin-bottom: 0.5rem;
}
.enc-modal-ta {
  resize: vertical;
  min-height: 120px;
}
.enc-modal-err {
  margin: 0 0 0.5rem;
  color: var(--danger);
  font-size: 0.78rem;
}
.enc-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.35rem;
}
.enc-modal-cancel,
.enc-modal-ok {
  padding: 0.38rem 0.75rem;
  border-radius: 8px;
  font: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--bg);
}
.enc-modal-ok {
  background: var(--accent);
  color: #fff;
  border-color: transparent;
  font-weight: 600;
}
.enc-modal-ok:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>

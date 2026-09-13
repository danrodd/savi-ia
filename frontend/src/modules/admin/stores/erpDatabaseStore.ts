/**
 * Pinia store de las bases del ERP (administración).
 *
 * El store ES la capa de datos (no hay vue-query). Las mutaciones
 * reemplazan la fila afectada con lo que devuelve el backend, salvo
 * `setDefault`, que cambia dos filas y por eso recarga la lista.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { erpDatabaseService } from '../services/erpDatabaseService'
import type { ErpDatabase, ErpDatabaseFormValues } from '../types'
import { toSaveRequest } from '../utils/erpDatabaseForm'

export const useErpDatabaseStore = defineStore('erpDatabases', () => {
  const databases = ref<ErpDatabase[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  function upsert(db: ErpDatabase): void {
    const index = databases.value.findIndex((d) => d.id === db.id)
    if (index === -1) databases.value.push(db)
    else databases.value.splice(index, 1, db)
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      databases.value = await erpDatabaseService.list(true)
    } catch (e) {
      error.value = (e as Error).message || 'No se pudieron cargar las bases de datos.'
    } finally {
      loading.value = false
    }
  }

  async function create(values: ErpDatabaseFormValues): Promise<ErpDatabase> {
    const created = await erpDatabaseService.create(toSaveRequest(values))
    upsert(created)
    return created
  }

  async function update(id: string, values: ErpDatabaseFormValues): Promise<ErpDatabase> {
    const updated = await erpDatabaseService.update(id, toSaveRequest(values))
    upsert(updated)
    return updated
  }

  async function setDefault(id: string): Promise<void> {
    await erpDatabaseService.setDefault(id)
    await load()
  }

  async function activate(id: string): Promise<void> {
    upsert(await erpDatabaseService.activate(id))
  }

  async function deactivate(id: string): Promise<void> {
    upsert(await erpDatabaseService.deactivate(id))
  }

  async function remove(id: string): Promise<void> {
    await erpDatabaseService.remove(id)
    databases.value = databases.value.filter((d) => d.id !== id)
  }

  return {
    databases,
    loading,
    error,
    load,
    create,
    update,
    setDefault,
    activate,
    deactivate,
    remove,
  }
})

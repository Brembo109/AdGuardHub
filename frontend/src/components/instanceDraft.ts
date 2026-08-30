import type { Instance } from '../api/types'

export interface InstanceDraft {
  name: string
  base_url: string
  username: string
  password: string
  verify_tls: boolean
}

export const BLANK_DRAFT: InstanceDraft = {
  name: '',
  base_url: 'http://',
  username: '',
  password: '',
  verify_tls: true,
}

export function draftFrom(instance: Instance): InstanceDraft {
  return {
    name: instance.name,
    base_url: instance.base_url,
    username: instance.username,
    // Never round-trips from the server; blank means "keep the stored one".
    password: '',
    verify_tls: instance.verify_tls,
  }
}

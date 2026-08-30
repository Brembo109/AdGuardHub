/** Onboarding completion is remembered per browser; the backend has no such notion. */
export const ONBOARDING_DONE_KEY = 'adguardhub.onboarding.done'

export function markOnboardingDone(): void {
  try {
    localStorage.setItem(ONBOARDING_DONE_KEY, '1')
  } catch {
    // Private mode or blocked storage: the flow just shows again next time.
  }
}

export function isOnboardingDone(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_DONE_KEY) === '1'
  } catch {
    return false
  }
}

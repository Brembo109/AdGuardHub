/**
 * Settings, as five pages behind one heading.
 *
 * It was one page with six cards stacked down it — timers, notifications,
 * backup, the account, refused sign-ins, updates — which is a list you scroll
 * rather than a place you navigate. They have nothing to do with each other,
 * so they are now separate routes and each can be linked to directly.
 */

import { Outlet } from 'react-router-dom'
import { SubTabs } from '../../components/SubTabs'
import { PageHeader } from '../../components/ui'
import { useT } from '../../i18n'
import { SETTINGS_TABS } from '../../nav'

export default function SettingsLayout() {
  const t = useT()
  return (
    <>
      <PageHeader
        title={t('Settings')}
        description={t(
          'How the hub itself behaves. The settings replicated to your instances live under Instances.',
        )}
      />
      <SubTabs tabs={SETTINGS_TABS} />
      <Outlet />
    </>
  )
}

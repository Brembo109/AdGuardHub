import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Instance } from '../api/types'
import { useAuth } from '../auth'
import { InstanceForm } from '../components/InstanceForm'
import { BLANK_DRAFT, type InstanceDraft } from '../components/instanceDraft'
import { Badge, Banner, Card, PageHeader } from '../components/ui'
import { errorMessage, useResource } from '../hooks/useApi'
import { useT } from '../i18n'

type Step = 1 | 2 | 3

/**
 * First-run walkthrough. It exists mainly to get the order right: instances first,
 * then adopt one as the master. Adding a rule before importing would push an empty
 * rule set over every instance's existing configuration.
 */
export default function Onboarding() {
  const t = useT()
  const navigate = useNavigate()
  const { state, refresh } = useAuth()
  const instances = useResource<Instance[]>(() => api.instances())
  const [step, setStep] = useState<Step>(1)
  const [draft, setDraft] = useState<InstanceDraft>({ ...BLANK_DRAFT })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const list = instances.data ?? []

  async function run(action: () => Promise<string>) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await action())
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
      await instances.reload()
    }
  }

  const addInstance = () =>
    run(async () => {
      const created = await api.createInstance(draft)
      setDraft({ ...BLANK_DRAFT })
      return t('Added {name}. Add another, or continue to the import step.', {
        name: created.name,
      })
    })

  const importFrom = (instance: Instance) => {
    if (
      !confirm(
        t('Use {name} as the master?', { name: instance.name }) +
          '\n\n' +
          t(
            "Its rules, subscriptions and instance settings become AdGuardHub's state, and every other instance is overwritten with them on the next push.",
          ) +
          '\n\n' +
          t(
            'Encryption is adopted but left switched off: enabling it on a node without a valid certificate would make that node unreachable.',
          ),
      )
    )
      return
    void run(async () => {
      const result = await api.importInstance(instance.id, { replace: true })
      setStep(3)
      const review = result.sections_needing_review.length
        ? ' ' +
          t(
            '{names} was adopted but left switched off — review it under Instance settings before enabling it.',
            { names: result.sections_needing_review.join(', ') },
          )
        : ''
      return (
        t(
          'Imported {rules} rule(s), {lists} subscription(s) and {sections} settings area(s) from {name}.',
          {
            rules: result.rules_imported,
            lists: result.filter_lists_imported,
            sections: result.sections_imported.length,
            name: result.instance,
          },
        ) + review
      )
    })
  }

  const finish = () =>
    void (async () => {
      try {
        await api.finishOnboarding()
      } catch (caught) {
        setError(errorMessage(caught))
        return
      }
      // The shell decides where "/" goes from the auth state, so re-read it
      // before navigating or the redirect sends us straight back here.
      await refresh()
      navigate('/')
    })()

  return (
    <>
      <PageHeader
        title={t('Welcome to AdGuardHub')}
        description={t('Three steps to a working hub. From then on every filtering change happens here, not in the native AdGuard UIs.')}
        actions={
          <button onClick={finish}>{t('Skip setup')}</button>
        }
      />

      {state?.ephemeral_secret ? (
        <Banner kind="warn">
          <strong>{t('Set ADGUARDHUB_SECRET_KEY before you add instances.')}</strong>{' '}
          {t(
            'Without it a random key is generated on every start, and the AdGuard passwords you are about to enter cannot be decrypted after the next restart.',
          )}
        </Banner>
      ) : null}

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}

      <ol className="steps">
        <StepRow n={1} current={step} title={t('Add your AdGuard Home instances')} onOpen={setStep}>
          <p className="hint">
            {t(
              'Every instance you have in DHCP as a DNS server belongs here — that is the whole point: a change made once reaches all of them, so a failover cannot undo it.',
            )}
          </p>
          <InstanceForm
            draft={draft}
            onChange={setDraft}
            onSubmit={addInstance}
            submitLabel={t('Add instance')}
            busy={busy}
          />
          {list.length ? (
            <div style={{ marginTop: 14 }}>
              <table>
                <tbody>
                  {list.map((instance) => (
                    <tr key={instance.id}>
                      <td>{instance.name}</td>
                      <td className="mono">{instance.base_url}</td>
                      <td>
                        <Badge tone={instance.status}>{t(instance.status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button
                className="primary"
                style={{ marginTop: 12 }}
                onClick={() => setStep(2)}
                disabled={busy}
              >
                {list.length === 1
                  ? t('Continue with 1 instance')
                  : t('Continue with {count} instances', { count: list.length })}
              </button>
            </div>
          ) : null}
        </StepRow>

        <StepRow n={2} current={step} title={t('Choose the master to import from')} onOpen={setStep}>
          <p className="hint">
            {t(
              "One instance's current configuration becomes the hub's starting state. The others are overwritten with it — there is no merge between instances, by design. Pick the one whose rules you actually want to keep.",
            )}
          </p>
          {list.length ? (
            <table>
              <tbody>
                {list.map((instance) => (
                  <tr key={instance.id}>
                    <td>{instance.name}</td>
                    <td className="mono">{instance.base_url}</td>
                    <td>
                      <Badge tone={instance.status}>{t(instance.status)}</Badge>
                    </td>
                    <td className="right">
                      <button
                        className="small primary"
                        onClick={() => importFrom(instance)}
                        disabled={busy || instance.status === 'unreachable'}
                      >
                        {t('Use as master')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="hint">{t('Add an instance in step 1 first.')}</p>
          )}
          <button style={{ marginTop: 12 }} onClick={() => setStep(3)} disabled={busy}>
            {t('Skip — I\'ll start from an empty rule set')}
          </button>
        </StepRow>

        <StepRow n={3} current={step} title={t('You\'re set up')} onOpen={setStep}>
          <p className="hint">
            {t(
              'AdGuardHub is now the single source of truth. Changes are pushed to every instance immediately; a reconciliation run catches anything that drifts and logs the correction.',
            )}
          </p>
          <ul className="hint" style={{ paddingLeft: 18 }}>
            <li>{t('Use the query log to allow a blocked domain everywhere in one click.')}</li>
            <li>{t('Add notification targets under Settings to hear about failures.')}</li>
            <li>{t('Stop making filtering changes in the native AdGuard UIs.')}</li>
          </ul>
          <button className="primary" onClick={finish}>
            {t('Go to the dashboard')}
          </button>
        </StepRow>
      </ol>
    </>
  )
}

function StepRow({
  n,
  current,
  title,
  onOpen,
  children,
}: {
  n: Step
  current: Step
  title: string
  onOpen: (step: Step) => void
  children: React.ReactNode
}) {
  const open = current === n
  return (
    <li className={`step${open ? ' open' : ''}${current > n ? ' done' : ''}`}>
      <button className="step-head" onClick={() => onOpen(n)}>
        <span className="step-n">{current > n ? '✓' : n}</span>
        {title}
      </button>
      {open ? <Card>{children}</Card> : null}
    </li>
  )
}

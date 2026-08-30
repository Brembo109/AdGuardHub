import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Instance } from '../api/types'
import { useAuth } from '../auth'
import { InstanceForm } from '../components/InstanceForm'
import { BLANK_DRAFT, type InstanceDraft } from '../components/instanceDraft'
import { markOnboardingDone } from '../onboarding'
import { Badge, Banner, Card, PageHeader } from '../components/ui'
import { errorMessage, useResource } from '../hooks/useApi'

type Step = 1 | 2 | 3

/**
 * First-run walkthrough. It exists mainly to get the order right: instances first,
 * then adopt one as the master. Adding a rule before importing would push an empty
 * rule set over every instance's existing configuration.
 */
export default function Onboarding() {
  const navigate = useNavigate()
  const { state } = useAuth()
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
      return `Added ${created.name}. Add another, or continue to the import step.`
    })

  const importFrom = (instance: Instance) => {
    if (
      !confirm(
        `Use ${instance.name} as the master?\n\n` +
          "Its rules and subscriptions become AdGuardHub's state, and every other instance is " +
          'overwritten with them on the next push.',
      )
    )
      return
    void run(async () => {
      const result = await api.importInstance(instance.id, { replace: true, include_dns: false })
      setStep(3)
      return `Imported ${result.rules_imported} rule(s) and ${result.filter_lists_imported} subscription(s) from ${result.instance}.`
    })
  }

  const finish = () => {
    markOnboardingDone()
    navigate('/')
  }

  return (
    <>
      <PageHeader
        title="Welcome to AdGuardHub"
        description="Three steps to a working hub. From then on every filtering change happens here, not in the native AdGuard UIs."
        actions={
          <button onClick={finish}>Skip setup</button>
        }
      />

      {state?.ephemeral_secret ? (
        <Banner kind="warn">
          <strong>Set ADGUARDHUB_SECRET_KEY before you add instances.</strong> Without it a random
          key is generated on every start, and the AdGuard passwords you are about to enter cannot
          be decrypted after the next restart.
        </Banner>
      ) : null}

      {error ? <Banner kind="error">{error}</Banner> : null}
      {message ? <Banner kind="ok">{message}</Banner> : null}

      <ol className="steps">
        <StepRow n={1} current={step} title="Add your AdGuard Home instances" onOpen={setStep}>
          <p className="hint">
            Every instance you have in DHCP as a DNS server belongs here — that is the whole point:
            a change made once reaches all of them, so a failover cannot undo it.
          </p>
          <InstanceForm
            draft={draft}
            onChange={setDraft}
            onSubmit={addInstance}
            submitLabel="Add instance"
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
                        <Badge tone={instance.status}>{instance.status}</Badge>
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
                Continue with {list.length} instance{list.length === 1 ? '' : 's'}
              </button>
            </div>
          ) : null}
        </StepRow>

        <StepRow n={2} current={step} title="Choose the master to import from" onOpen={setStep}>
          <p className="hint">
            One instance's current configuration becomes the hub's starting state. The others are
            overwritten with it — there is no merge between instances, by design. Pick the one whose
            rules you actually want to keep.
          </p>
          {list.length ? (
            <table>
              <tbody>
                {list.map((instance) => (
                  <tr key={instance.id}>
                    <td>{instance.name}</td>
                    <td className="mono">{instance.base_url}</td>
                    <td>
                      <Badge tone={instance.status}>{instance.status}</Badge>
                    </td>
                    <td className="right">
                      <button
                        className="small primary"
                        onClick={() => importFrom(instance)}
                        disabled={busy || instance.status === 'unreachable'}
                      >
                        Use as master
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="hint">Add an instance in step 1 first.</p>
          )}
          <button style={{ marginTop: 12 }} onClick={() => setStep(3)} disabled={busy}>
            Skip — I'll start from an empty rule set
          </button>
        </StepRow>

        <StepRow n={3} current={step} title="You're set up" onOpen={setStep}>
          <p className="hint">
            AdGuardHub is now the single source of truth. Changes are pushed to every instance
            immediately; a reconciliation run catches anything that drifts and logs the correction.
          </p>
          <ul className="hint" style={{ paddingLeft: 18 }}>
            <li>Use the query log to allow a blocked domain everywhere in one click.</li>
            <li>Add notification targets under Settings to hear about failures.</li>
            <li>Stop making filtering changes in the native AdGuard UIs.</li>
          </ul>
          <button className="primary" onClick={finish}>
            Go to the dashboard
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

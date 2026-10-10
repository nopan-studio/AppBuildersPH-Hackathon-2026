import { useEffect, useMemo, useState } from 'react'
import { useStyletron } from 'baseui'
import { Button } from 'baseui/button'
import { Input } from 'baseui/input'
import { Select } from 'baseui/select'
import { Card } from 'baseui/card'
import { Tag } from 'baseui/tag'
import { Spinner } from 'baseui/spinner'
import { Notification } from 'baseui/notification'
import { Table } from 'baseui/table'
import { FileUploaderBasic } from 'baseui/file-uploader-basic'
import {
  DisplayXSmall,
  LabelLarge,
  LabelMedium,
  ParagraphSmall,
} from 'baseui/typography'
import { exportXlsx, getHealth, scan } from './api.js'

const TIERS = [
  { id: 'tiny', label: 'tiny (fastest)' },
  { id: 'small', label: 'small (default)' },
  { id: 'medium', label: 'medium (accurate)' },
]

function money(value) {
  return value === null || value === undefined ? '—' : Number(value).toFixed(2)
}

function ResultCard({ result, imageUrl }) {
  const [css, theme] = useStyletron()
  const accepted = result.status === 'accepted'
  const items = result.items || []
  const reasons = result.review_reasons || []

  const wrap = css({ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '8px' })
  const meta = css({
    color: theme.colors.contentSecondary,
    marginTop: '8px',
    marginBottom: '8px',
  })
  const columns = css({
    display: 'flex',
    flexWrap: 'wrap',
    gap: '20px',
    marginTop: '12px',
    alignItems: 'flex-start',
  })
  const figure = css({ flex: '1 1 280px', maxWidth: '360px' })
  const figureImg = css({
    width: '100%',
    display: 'block',
    borderRadius: theme.borders.radius200,
    border: `1px solid ${theme.colors.borderOpaque}`,
    background: theme.colors.backgroundSecondary,
  })
  const placeholder = css({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '220px',
    borderRadius: theme.borders.radius200,
    border: `1px dashed ${theme.colors.borderOpaque}`,
    color: theme.colors.contentTertiary,
    fontSize: '13px',
  })
  const caption = css({
    color: theme.colors.contentTertiary,
    marginTop: '6px',
    textAlign: 'center',
  })
  const dataCol = css({ flex: '2 1 380px', minWidth: '280px' })

  return (
    <Card
      overrides={{
        Root: { style: { marginBottom: '16px' } },
      }}
    >
      <div
        className={css({
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
        })}
      >
        <LabelLarge>{result.file}</LabelLarge>
        <Tag kind={accepted ? 'positive' : 'warning'} closeable={false}>
          {result.status}
        </Tag>
      </div>

      <div className={columns}>
        <div className={figure}>
          {imageUrl ? (
            <a href={imageUrl} target="_blank" rel="noreferrer">
              <img src={imageUrl} alt={result.file} className={figureImg} />
            </a>
          ) : (
            <div className={placeholder}>Original image unavailable</div>
          )}
          <ParagraphSmall className={caption}>
            Original receipt · click to enlarge
          </ParagraphSmall>
        </div>

        <div className={dataCol}>
          <ParagraphSmall className={meta}>
            <strong>Merchant</strong> {result.merchant || '—'} &nbsp;·&nbsp;
            <strong>Date</strong> {result.date || '—'} &nbsp;·&nbsp;
            <strong>Currency</strong> {result.currency || '—'}
          </ParagraphSmall>
          <ParagraphSmall className={meta}>
            <strong>Subtotal</strong> {money(result.subtotal)} &nbsp;·&nbsp;
            <strong>Tax</strong> {money(result.tax)}
            {result.tax_inclusive ? ' (incl.)' : ''} &nbsp;·&nbsp;
            <strong>Total</strong> {money(result.total)} &nbsp;·&nbsp;
            <strong>OCR conf</strong>{' '}
            {Number(result.ocr_mean_conf || 0).toFixed(2)}
          </ParagraphSmall>

          {items.length > 0 && (
            <Table
              columns={['Item', 'Qty', 'Unit', 'Amount']}
              data={items.map((item) => [
                item.name || '—',
                item.qty === null || item.qty === undefined ? '—' : item.qty,
                money(item.unit_price),
                money(item.amount),
              ])}
            />
          )}

          {reasons.length > 0 && (
            <div className={wrap}>
              {reasons.map((reason) => (
                <Tag key={reason} kind="warning" closeable={false}>
                  {reason}
                </Tag>
              ))}
            </div>
          )}

          <details className={css({ marginTop: '12px' })}>
            <summary className={css({ cursor: 'pointer' })}>Raw JSON</summary>
            <pre
              className={css({
                background: theme.colors.backgroundSecondary,
                borderRadius: theme.borders.radius200,
                padding: theme.sizing.scale400,
                overflowX: 'auto',
                fontSize: '12px',
              })}
            >
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </Card>
  )
}

export default function App() {
  const [css, theme] = useStyletron()

  const [files, setFiles] = useState([])
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [health, setHealth] = useState(null)

  const [model, setModel] = useState('qwen3:1.7b')
  const [ocrTier, setOcrTier] = useState('small')
  const [minConf, setMinConf] = useState('0.80')

  useEffect(() => {
    let active = true
    getHealth(model)
      .then((data) => active && setHealth(data))
      .catch((err) => active && setHealth({ ok: false, message: err.message }))
    return () => {
      active = false
    }
  }, [model])

  // Object URLs for the selected files, used to show the image beside results.
  const previews = useMemo(
    () => files.map((file) => URL.createObjectURL(file)),
    [files],
  )

  useEffect(() => {
    return () => previews.forEach((url) => URL.revokeObjectURL(url))
  }, [previews])

  const addFiles = (accepted) => {
    setError(null)
    setResults(null)
    setFiles((current) => {
      const seen = new Set(current.map((f) => `${f.name}:${f.size}`))
      const next = accepted.filter((f) => !seen.has(`${f.name}:${f.size}`))
      return [...current, ...next]
    })
  }

  const removeFile = (index) => {
    setResults(null)
    setFiles((current) => current.filter((_, i) => i !== index))
  }

  const runScan = async () => {
    setLoading(true)
    setError(null)
    setResults(null)
    try {
      const data = await scan(files, {
        model,
        ocrTier,
        minConf: Number(minConf),
      })
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const downloadXlsx = async () => {
    if (!results) return
    try {
      await exportXlsx(results.results)
    } catch (err) {
      setError(err.message)
    }
  }

  const page = css({ maxWidth: '1120px', margin: '0 auto', padding: '40px 24px' })
  const card = css({ marginBottom: '24px' })
  const field = css({ marginBottom: '16px' })
  const twoCol = css({
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: '16px',
  })
  const chips = css({ display: 'flex', flexWrap: 'wrap', gap: '8px' })
  const chip = css({
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 12px',
    background: theme.colors.backgroundSecondary,
    borderRadius: theme.borders.radius300,
    fontSize: '13px',
  })
  const link = css({ cursor: 'pointer', color: theme.colors.contentSecondary })
  const center = css({
    display: 'flex',
    justifyContent: 'center',
    padding: '40px',
  })

  const healthKind = health && health.ok ? 'positive' : 'warning'
  const acceptedCount = useMemo(
    () => (results ? results.results.filter((r) => r.status === 'accepted').length : 0),
    [results],
  )

  return (
    <div className={page}>
      <DisplayXSmall>Bookyp</DisplayXSmall>
      <ParagraphSmall
        className={css({ color: theme.colors.contentSecondary, marginTop: '8px' })}
      >
        Offline OCR + local LLM. Upload receipt images and get validated JSON.
      </ParagraphSmall>

      <div className={css({ height: '24px' })} />

      {health && (
        <div className={card}>
          <Notification kind={healthKind}>
            {health.ok
              ? `${health.message}`
              : `${health.message} (run bookyp check)`}
          </Notification>
        </div>
      )}

      <Card overrides={{ Root: { style: { marginBottom: '24px' } } }}>
        <FileUploaderBasic
          accept={['image/*']}
          multiple
          onDropAccepted={addFiles}
          onDropRejected={() => setError('Only image files are supported.')}
          buttonText="Browse files"
          contentMessage="Drag and drop receipt images, or browse"
        />

        {files.length > 0 && (
          <div className={chips} style={{ marginTop: '16px' }}>
            {files.map((file, index) => (
              <span key={`${file.name}-${index}`} className={chip}>
                {file.name}
                <span
                  className={link}
                  role="button"
                  tabIndex={0}
                  onClick={() => removeFile(index)}
                  onKeyDown={(e) => e.key === 'Enter' && removeFile(index)}
                >
                  ✕
                </span>
              </span>
            ))}
          </div>
        )}

        <div className={css({ height: '24px' })} />

        <div className={twoCol}>
          <div className={field}>
            <LabelMedium className={css({ marginBottom: '8px' })}>
              Ollama model
            </LabelMedium>
            <Input
              value={model}
              onChange={(e) => setModel(e.currentTarget.value)}
              placeholder="qwen3:1.7b"
              clearable
            />
          </div>
          <div className={field}>
            <LabelMedium className={css({ marginBottom: '8px' })}>
              OCR tier
            </LabelMedium>
            <Select
              options={TIERS}
              value={TIERS.filter((t) => t.id === ocrTier)}
              onChange={({ value }) => setOcrTier(value[0]?.id || 'small')}
              clearable={false}
            />
          </div>
          <div className={field}>
            <LabelMedium className={css({ marginBottom: '8px' })}>
              Min OCR confidence
            </LabelMedium>
            <Input
              value={minConf}
              type="number"
              step="0.05"
              min="0"
              max="1"
              onChange={(e) => setMinConf(e.currentTarget.value)}
            />
          </div>
        </div>

        <Button
          onClick={runScan}
          isLoading={loading}
          disabled={files.length === 0 || loading}
          overrides={{ BaseButton: { style: { width: '100%' } } }}
        >
          {loading ? 'Scanning…' : `Scan ${files.length || ''} receipt${files.length === 1 ? '' : 's'}`}
        </Button>
      </Card>

      {error && (
        <div className={card}>
          <Notification kind="negative">{error}</Notification>
        </div>
      )}

      {loading && (
        <div className={center}>
          <Spinner />
        </div>
      )}

      {results && !loading && (
        <>
          <div
            className={css({
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '12px',
              flexWrap: 'wrap',
              marginBottom: '16px',
            })}
          >
            <LabelLarge>
              {acceptedCount}/{results.results.length} accepted · model{' '}
              {results.model} · OCR {results.ocr_tier} on {results.ocr_device}
            </LabelLarge>
            <Button kind="secondary" size="compact" onClick={downloadXlsx}>
              Export to Excel
            </Button>
          </div>
          {results.results.map((result, index) => (
            <ResultCard
              key={`${result.file}-${index}`}
              result={result}
              imageUrl={previews[index]}
            />
          ))}
        </>
      )}

      <div
        className={css({
          marginTop: '48px',
          textAlign: 'center',
          color: theme.colors.contentTertiary,
        })}
      >
        <ParagraphSmall>Built for APPBuilders PH Hackathon 2026</ParagraphSmall>
      </div>
    </div>
  )
}

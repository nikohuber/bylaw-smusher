import { useState } from 'react'

interface Props {
  onSubmit: (question: string) => void
  loading: boolean
}

export default function QuestionInput({ onSubmit, loading }: Props) {
  const [value, setValue] = useState('')

  const submit = () => {
    const q = value.trim()
    if (q) {
      onSubmit(q)
      setValue('')
    }
  }

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <textarea
        rows={3}
        style={{ flex: 1, padding: 8, fontSize: 14, resize: 'vertical' }}
        placeholder="Ask about zoning rules, setbacks, permits, height limits…"
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
        disabled={loading}
      />
      <button
        onClick={submit}
        disabled={loading || !value.trim()}
        style={{ padding: '0 16px', fontSize: 14 }}
      >
        {loading ? 'Thinking…' : 'Ask'}
      </button>
    </div>
  )
}

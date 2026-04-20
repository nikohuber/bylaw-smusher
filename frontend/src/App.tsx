import { useState } from 'react'
import QuestionInput from './components/QuestionInput'
import AnswerCard from './components/AnswerCard'

interface Source {
  page: number
  source: string
  preview: string
}

interface Result {
  question: string
  answer: string
  sources: Source[]
}

export default function App() {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<Result[]>([])
  const [error, setError] = useState<string | null>(null)

  async function handleQuestion(question: string) {
    setLoading(true)
    setError(null)
    let answer = ''
    let sources: Source[] = []

    try {
      const resp = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`)

      const rawSources = resp.headers.get('X-Sources')
      if (rawSources) sources = JSON.parse(rawSources)

      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        answer += decoder.decode(value, { stream: true })
      }
    } catch (e) {
      setError(String(e))
      setLoading(false)
      return
    }

    setResults(prev => [{ question, answer, sources }, ...prev])
    setLoading(false)
  }

  return (
    <div style={{ maxWidth: 760, margin: '40px auto', padding: '0 16px', fontFamily: 'sans-serif' }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>Bylaw Smusher</h1>
      <p style={{ color: '#666', marginTop: 0, marginBottom: 24, fontSize: 14 }}>
        Ask plain-language questions about your municipality's zoning bylaws.
      </p>
      <QuestionInput onSubmit={handleQuestion} loading={loading} />
      {error && <p style={{ color: 'red', marginTop: 12 }}>{error}</p>}
      {results.map((r, i) => (
        <AnswerCard key={i} question={r.question} answer={r.answer} sources={r.sources} />
      ))}
    </div>
  )
}

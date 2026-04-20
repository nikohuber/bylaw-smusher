interface Source {
  page: number
  source: string
  preview: string
}

interface Props {
  question: string
  answer: string
  sources: Source[]
}

export default function AnswerCard({ question, answer, sources }: Props) {
  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 6, padding: 16, marginTop: 16 }}>
      <p style={{ fontWeight: 600, marginTop: 0 }}>{question}</p>
      <p style={{ whiteSpace: 'pre-wrap' }}>{answer}</p>
      {sources.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, color: '#555' }}>
            {sources.length} source excerpt{sources.length !== 1 ? 's' : ''}
          </summary>
          {sources.map((s, i) => (
            <div key={i} style={{ marginTop: 8, fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
              <strong>{s.source}</strong> — p.{s.page}<br />
              <em>{s.preview}</em>
            </div>
          ))}
        </details>
      )}
    </div>
  )
}

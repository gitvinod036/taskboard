import { useEffect, useRef } from 'react'
import Editor, { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'

// Keep Monaco self-contained (no CDN worker fetch) so the app works offline
// and behind strict CSPs.
loader.config({ monaco })

/**
 * Thin Monaco wrapper used by the coding workspace.
 *
 * This component only EDITS text. It never runs, evaluates or transpiles the
 * code it holds — execution belongs to the Phase 3 backend sandbox.
 */
export default function CodeEditor({ value, language, onChange, height = 380 }) {
  const editorRef = useRef(null)

  useEffect(() => {
    return () => {
      if (editorRef.current) {
        editorRef.current.dispose()
        editorRef.current = null
      }
    }
  }, [])

  function handleMount(editor) {
    editorRef.current = editor
  }

  return (
    <div className="code-editor-shell">
      <Editor
        height={height}
        theme="vs-dark"
        language={language}
        value={value}
        onChange={(next) => onChange(next ?? '')}
        onMount={handleMount}
        loading={<p className="state-message">Loading editor…</p>}
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 4,
          wordWrap: 'on',
          renderWhitespace: 'none',
          readOnly: false,
        }}
      />
    </div>
  )
}

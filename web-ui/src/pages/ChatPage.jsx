import { useState, useRef, useEffect } from 'react'
import {
  IonPage,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonContent,
  IonFooter,
  IonTextarea,
  IonButton,
  IonIcon,
  IonSpinner,
  IonCard,
  IonCardContent
} from '@ionic/react'
import { send, trash, refresh } from 'ionicons/icons'
import { useAuth } from '../context/AuthContext'

function ChatPage() {
  const { authFetch } = useAuth()
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [error, setError] = useState(null)
  const contentRef = useRef(null)

  // Scroll to bottom when messages change
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollToBottom(300)
    }
  }, [messages])

  const sendMessage = async () => {
    const text = inputText.trim()
    if (!text || loading) return

    // Add user message
    const userMessage = { role: 'user', content: text }
    setMessages(prev => [...prev, userMessage])
    setInputText('')
    setLoading(true)
    setError(null)

    try {
      const response = await authFetch('/api/v1/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: text,
          session_id: sessionId
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Request failed: ${response.statusText}`)
      }

      const data = await response.json()

      // Save session ID for conversation continuity
      if (data.session_id) {
        setSessionId(data.session_id)
      }

      // Add assistant message
      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        toolCalls: data.tool_calls || []
      }
      setMessages(prev => [...prev, assistantMessage])

    } catch (err) {
      console.error('Chat error:', err)
      setError(err.message)
      // Add error message to chat
      setMessages(prev => [...prev, {
        role: 'error',
        content: err.message
      }])
    } finally {
      setLoading(false)
    }
  }

  const clearChat = async () => {
    // Delete session on server if we have one
    if (sessionId) {
      try {
        await authFetch(`/api/v1/chat/${sessionId}`, {
          method: 'DELETE'
        })
      } catch (err) {
        console.error('Error deleting session:', err)
      }
    }

    setMessages([])
    setSessionId(null)
    setError(null)
  }

  const handleKeyPress = (e) => {
    // Send on Enter (but not Shift+Enter for new lines)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <div slot="start" style={{ display: 'flex', alignItems: 'center', marginLeft: '10px' }}>
            <img src="/ALFRD.svg" alt="ALFRD Logo" style={{ height: '32px', width: 'auto' }} />
          </div>
          <IonTitle>Chat</IonTitle>
          <IonButton slot="end" fill="clear" onClick={clearChat} title="Clear chat">
            <IonIcon icon={trash} />
          </IonButton>
        </IonToolbar>
      </IonHeader>

      <IonContent ref={contentRef} className="chat-content">
        <div style={{ padding: '10px', paddingBottom: '80px' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: '#666' }}>
              <h3 style={{ marginBottom: '10px' }}>Ask ALFRD</h3>
              <p style={{ fontSize: '0.9em', lineHeight: '1.5' }}>
                I can help you find and analyze your documents.
              </p>
              <div style={{ marginTop: '20px', textAlign: 'left', maxWidth: '300px', margin: '20px auto' }}>
                <p style={{ fontSize: '0.85em', color: '#888', marginBottom: '10px' }}>Try asking:</p>
                <ul style={{ fontSize: '0.85em', color: '#888', paddingLeft: '20px', margin: 0 }}>
                  <li>"What series do I have?"</li>
                  <li>"Show me my utility bills"</li>
                  <li>"What was my highest bill?"</li>
                  <li>"Search for insurance documents"</li>
                </ul>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '10px'
              }}
            >
              <IonCard
                style={{
                  maxWidth: '85%',
                  margin: 0,
                  backgroundColor: msg.role === 'user'
                    ? 'var(--ion-color-primary)'
                    : msg.role === 'error'
                      ? 'var(--ion-color-danger)'
                      : 'var(--ion-color-light)'
                }}
              >
                <IonCardContent
                  style={{
                    padding: '12px 16px',
                    color: msg.role === 'user' || msg.role === 'error'
                      ? 'white'
                      : 'inherit'
                  }}
                >
                  <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {msg.content}
                  </div>

                  {/* Show tool calls for debugging if any */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div style={{
                      marginTop: '8px',
                      paddingTop: '8px',
                      borderTop: '1px solid rgba(0,0,0,0.1)',
                      fontSize: '0.75em',
                      color: '#888'
                    }}>
                      Tools used: {msg.toolCalls.map(t => t.name).join(', ')}
                    </div>
                  )}
                </IonCardContent>
              </IonCard>
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '10px' }}>
              <IonCard style={{ margin: 0, backgroundColor: 'var(--ion-color-light)' }}>
                <IonCardContent style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <IonSpinner name="dots" />
                  <span style={{ color: '#666' }}>Thinking...</span>
                </IonCardContent>
              </IonCard>
            </div>
          )}
        </div>
      </IonContent>

      <IonFooter>
        <IonToolbar style={{ padding: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px' }}>
            <IonTextarea
              value={inputText}
              onIonInput={(e) => setInputText(e.detail.value || '')}
              onKeyDown={handleKeyPress}
              placeholder="Ask about your documents..."
              autoGrow={true}
              rows={1}
              maxlength={2000}
              style={{
                flex: 1,
                backgroundColor: 'var(--ion-color-light)',
                borderRadius: '20px',
                padding: '8px 16px',
                margin: 0,
                '--padding-start': '16px',
                '--padding-end': '16px'
              }}
            />
            <IonButton
              onClick={sendMessage}
              disabled={!inputText.trim() || loading}
              style={{ marginBottom: '4px' }}
            >
              <IonIcon icon={send} />
            </IonButton>
          </div>
        </IonToolbar>
      </IonFooter>
    </IonPage>
  )
}

export default ChatPage

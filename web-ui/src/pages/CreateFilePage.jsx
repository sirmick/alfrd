import { useState, useEffect } from 'react'
import {
  IonPage,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonContent,
  IonButton,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonIcon,
  IonSpinner,
  IonBackButton,
  IonButtons,
  IonInput,
  IonChip,
  IonToast,
  IonSelect,
  IonSelectOption,
  IonLabel
} from '@ionic/react'
import { add, close } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

function CreateFilePage() {
  const history = useHistory()
  const { authFetch } = useAuth()
  const [tags, setTags] = useState([])
  const [tagInput, setTagInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [availableTags, setAvailableTags] = useState([])
  const [toast, setToast] = useState({ show: false, message: '' })

  useEffect(() => {
    fetchAvailableTags()
  }, [])

  const fetchAvailableTags = async () => {
    try {
      // Fetch all documents to extract popular tags
      const response = await authFetch('/api/v1/documents?limit=100&status=completed')
      if (!response.ok) {
        throw new Error('Failed to fetch documents')
      }
      const data = await response.json()
      
      // Extract unique tags
      const tagSet = new Set()
      data.documents.forEach(doc => {
        if (doc.tags && Array.isArray(doc.tags)) {
          doc.tags.forEach(tag => tagSet.add(tag))
        }
      })
      
      setAvailableTags(Array.from(tagSet).sort())
    } catch (err) {
      console.error('Error fetching tags:', err)
    }
  }

  const handleAddTag = () => {
    if (tagInput.trim() && !tags.includes(tagInput.trim())) {
      setTags([...tags, tagInput.trim()])
      setTagInput('')
    }
  }

  const handleRemoveTag = (tag) => {
    setTags(tags.filter(t => t !== tag))
  }

  const handleCreate = async () => {
    if (tags.length === 0) {
      setToast({ show: true, message: 'Please add at least one tag' })
      return
    }

    try {
      setLoading(true)
      
      // Build query string (no document_type needed - tags only!)
      const params = new URLSearchParams()
      tags.forEach(tag => params.append('tags', tag))

      const url = `/api/v1/files/create?${params.toString()}`

      const response = await authFetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('API error:', errorText)
        throw new Error(`Failed to create file: ${response.statusText}`)
      }

      const data = await response.json()
      
      setToast({ show: true, message: 'File created successfully!' })
      
      // Navigate to file detail after a short delay
      setTimeout(() => {
        history.push(`/files/${data.file.id}`)
      }, 1000)
      
    } catch (err) {
      console.error('Error creating file:', err)
      setToast({ show: true, message: `Error: ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/files" />
          </IonButtons>
          <IonTitle>Create File</IonTitle>
        </IonToolbar>
      </IonHeader>
      
      <IonContent>
        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Create a File</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            <p>Files automatically include all documents matching the selected tags.</p>
            <p style={{ fontSize: '0.9em', color: '#666', marginTop: '8px' }}>
              💡 Tip: Add document type tags (like "bill" or "finance") to filter by type.
            </p>
          </IonCardContent>
        </IonCard>

        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Tags</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            {tags.length > 0 && (
              <div style={{ marginBottom: '16px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {tags.map((tag) => (
                  <IonChip key={tag} onClick={() => handleRemoveTag(tag)}>
                    <IonLabel>{tag}</IonLabel>
                    <IonIcon icon={close} />
                  </IonChip>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <IonInput
                value={tagInput}
                placeholder="Enter tag name"
                onIonInput={(e) => setTagInput(e.detail.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAddTag()}
                style={{ border: '1px solid #ddd', borderRadius: '4px', padding: '8px' }}
              />
              <IonButton onClick={handleAddTag} disabled={!tagInput.trim()}>
                <IonIcon icon={add} />
              </IonButton>
            </div>

            {availableTags.length > 0 && (
              <div>
                <p style={{ fontSize: '0.9em', color: '#666', marginBottom: '8px' }}>
                  Available tags:
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {availableTags.map((tag) => (
                    <IonChip
                      key={tag}
                      color="primary"
                      outline
                      onClick={() => {
                        if (!tags.includes(tag)) {
                          setTags([...tags, tag])
                        }
                      }}
                      disabled={tags.includes(tag)}
                    >
                      <IonLabel>{tag}</IonLabel>
                      <IonIcon icon={add} />
                    </IonChip>
                  ))}
                </div>
              </div>
            )}

            <p style={{ fontSize: '0.85em', color: '#666', marginTop: '16px' }}>
              File signature: {tags.sort().join(':')}
            </p>
          </IonCardContent>
        </IonCard>

        <div style={{ padding: '16px' }}>
          <IonButton
            expand="block"
            onClick={handleCreate}
            disabled={tags.length === 0 || loading}
          >
            {loading ? <IonSpinner name="crescent" /> : 'Create File'}
          </IonButton>
        </div>

        <IonToast
          isOpen={toast.show}
          onDidDismiss={() => setToast({ show: false, message: '' })}
          message={toast.message}
          duration={2000}
        />
      </IonContent>
    </IonPage>
  )
}

export default CreateFilePage
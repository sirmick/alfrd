import { useState } from 'react'
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
  IonToast,
  IonButtons,
  IonBackButton
} from '@ionic/react'
import { camera } from 'ionicons/icons'
import { Camera, CameraResultType } from '@capacitor/camera'
import { useHistory } from 'react-router-dom'

function CapturePage() {
  const history = useHistory()
  const [photo, setPhoto] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [toast, setToast] = useState({ show: false, message: '', color: 'success' })

  const takePhoto = async () => {
    try {
      const image = await Camera.getPhoto({
        quality: 90,
        allowEditing: false,
        resultType: CameraResultType.Base64
      })
      
      setPhoto({
        base64: image.base64String,
        format: image.format
      })
      
      setToast({ show: true, message: 'Photo captured!', color: 'success' })
    } catch (error) {
      console.error('Camera error:', error)
      setToast({ show: true, message: 'Failed to capture photo', color: 'danger' })
    }
  }

  const uploadPhoto = async () => {
    if (!photo) return

    setUploading(true)
    console.log('[Upload] Starting photo upload...')
    console.log('[Upload] Photo format:', photo.format)
    console.log('[Upload] Base64 length:', photo.base64?.length || 0)
    
    try {
      // Convert base64 to blob
      console.log('[Upload] Converting base64 to blob...')
      const base64Response = await fetch(`data:image/${photo.format};base64,${photo.base64}`)
      const blob = await base64Response.blob()
      console.log('[Upload] Blob created:', blob.size, 'bytes, type:', blob.type)
      
      // Create form data
      const formData = new FormData()
      formData.append('file', blob, `photo.${photo.format}`)
      console.log('[Upload] FormData created with file:', `photo.${photo.format}`)
      
      // Upload to API
      console.log('[Upload] Sending POST to /api/v1/documents/upload-image...')
      const response = await fetch('/api/v1/documents/upload-image', {
        method: 'POST',
        body: formData
      })
      
      console.log('[Upload] Response status:', response.status, response.statusText)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('[Upload] Error response body:', errorText)
        throw new Error(`Upload failed: ${response.statusText} - ${errorText}`)
      }
      
      const result = await response.json()
      console.log('[Upload] Upload successful! Result:', result)
      
      setToast({ show: true, message: `Document uploaded successfully! ID: ${result.document_id}`, color: 'success' })
      setPhoto(null)
      
      // Redirect to documents list after short delay
      setTimeout(() => {
        console.log('[Upload] Redirecting to /documents')
        history.push('/documents')
      }, 1500)
    } catch (error) {
      console.error('[Upload] Upload error:', error)
      console.error('[Upload] Error stack:', error.stack)
      setToast({ show: true, message: `Upload failed: ${error.message}`, color: 'danger' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/documents" />
          </IonButtons>
          <IonTitle>Capture Document</IonTitle>
        </IonToolbar>
      </IonHeader>
      
      <IonContent className="ion-padding">
        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Take Photo</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            <IonButton expand="block" onClick={takePhoto}>
              <IonIcon slot="start" icon={camera} />
              Take Photo
            </IonButton>
            
            {photo && (
              <div style={{ marginTop: '20px' }}>
                <img 
                  src={`data:image/${photo.format};base64,${photo.base64}`}
                  alt="Captured document"
                  style={{ width: '100%', maxHeight: '400px', objectFit: 'contain' }}
                />
                <IonButton 
                  expand="block" 
                  color="primary" 
                  onClick={uploadPhoto}
                  disabled={uploading}
                  style={{ marginTop: '10px' }}
                >
                  {uploading ? 'Uploading...' : 'Upload Document'}
                </IonButton>
                <IonButton 
                  expand="block" 
                  color="light" 
                  onClick={() => setPhoto(null)}
                  disabled={uploading}
                >
                  Cancel
                </IonButton>
              </div>
            )}
          </IonCardContent>
        </IonCard>
        
        <IonToast
          isOpen={toast.show}
          message={toast.message}
          duration={3000}
          color={toast.color}
          onDidDismiss={() => setToast({ ...toast, show: false })}
        />
      </IonContent>
    </IonPage>
  )
}

export default CapturePage
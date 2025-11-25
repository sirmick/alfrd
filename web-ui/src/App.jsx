import { useState } from 'react'
import { 
  IonApp, 
  IonHeader, 
  IonToolbar, 
  IonTitle, 
  IonContent, 
  IonPage,
  IonButton,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonIcon,
  IonToast,
  setupIonicReact
} from '@ionic/react'
import { camera } from 'ionicons/icons'
import { Camera, CameraResultType } from '@capacitor/camera'

// Initialize Ionic
setupIonicReact()

function App() {
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
    try {
      // Convert base64 to blob
      const base64Response = await fetch(`data:image/${photo.format};base64,${photo.base64}`)
      const blob = await base64Response.blob()
      
      // Create form data
      const formData = new FormData()
      formData.append('file', blob, `photo.${photo.format}`)
      
      // Upload to API
      const response = await fetch('/api/v1/documents/upload-image', {
        method: 'POST',
        body: formData
      })
      
      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`)
      }
      
      const result = await response.json()
      console.log('Upload result:', result)
      
      setToast({ show: true, message: `Document uploaded! ID: ${result.document_id}`, color: 'success' })
      setPhoto(null) // Clear photo after successful upload
    } catch (error) {
      console.error('Upload error:', error)
      setToast({ show: true, message: `Upload failed: ${error.message}`, color: 'danger' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <IonApp>
      <IonPage>
        <IonHeader>
          <IonToolbar>
            <IonTitle>ALFRD - Document Scanner</IonTitle>
          </IonToolbar>
        </IonHeader>
        
        <IonContent className="ion-padding">
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>Capture Document</IonCardTitle>
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
    </IonApp>
  )
}

export default App
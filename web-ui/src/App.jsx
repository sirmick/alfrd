import { IonApp, setupIonicReact } from '@ionic/react'
import { IonReactRouter } from '@ionic/react-router'

import { AuthProvider } from './context/AuthContext'
import TabBar from './components/TabBar'

// Initialize Ionic
setupIonicReact()

function App() {
  return (
    <IonApp>
      <AuthProvider>
        <IonReactRouter>
          <TabBar />
        </IonReactRouter>
      </AuthProvider>
    </IonApp>
  )
}

export default App
import { IonApp, setupIonicReact } from '@ionic/react'
import { IonReactRouter } from '@ionic/react-router'

import TabBar from './components/TabBar'

// Initialize Ionic
setupIonicReact()

function App() {
  return (
    <IonApp>
      <IonReactRouter>
        <TabBar />
      </IonReactRouter>
    </IonApp>
  )
}

export default App
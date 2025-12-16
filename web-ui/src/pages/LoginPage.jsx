import React, { useState } from 'react';
import {
  IonPage,
  IonContent,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonItem,
  IonLabel,
  IonInput,
  IonButton,
  IonSpinner,
  IonText,
  IonIcon
} from '@ionic/react';
import { logInOutline, lockClosedOutline, personOutline } from 'ionicons/icons';
import { useHistory } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const LoginPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login } = useAuth();
  const history = useHistory();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(username, password);
      history.replace('/documents');
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <IonPage>
      <IonContent className="ion-padding" fullscreen>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100%',
          padding: '20px'
        }}>
          <div style={{
            textAlign: 'center',
            marginBottom: '30px'
          }}>
            <h1 style={{
              fontSize: '2.5rem',
              fontWeight: 'bold',
              color: 'var(--ion-color-primary)',
              margin: '0 0 10px 0'
            }}>
              ALFRD
            </h1>
            <p style={{
              color: 'var(--ion-color-medium)',
              margin: 0
            }}>
              AI Document Management
            </p>
          </div>

          <IonCard style={{ width: '100%', maxWidth: '400px' }}>
            <IonCardHeader>
              <IonCardTitle style={{ textAlign: 'center' }}>
                <IonIcon icon={lockClosedOutline} style={{ marginRight: '8px' }} />
                Sign In
              </IonCardTitle>
            </IonCardHeader>

            <IonCardContent>
              <form onSubmit={handleSubmit}>
                {error && (
                  <IonText color="danger">
                    <p style={{
                      padding: '10px',
                      background: 'var(--ion-color-danger-tint)',
                      borderRadius: '8px',
                      margin: '0 0 16px 0'
                    }}>
                      {error}
                    </p>
                  </IonText>
                )}

                <IonItem lines="full" style={{ marginBottom: '16px' }}>
                  <IonIcon icon={personOutline} slot="start" color="medium" />
                  <IonInput
                    type="text"
                    placeholder="Username"
                    value={username}
                    onIonInput={(e) => setUsername(e.detail.value)}
                    required
                    disabled={loading}
                  />
                </IonItem>

                <IonItem lines="full" style={{ marginBottom: '24px' }}>
                  <IonIcon icon={lockClosedOutline} slot="start" color="medium" />
                  <IonInput
                    type="password"
                    placeholder="Password"
                    value={password}
                    onIonInput={(e) => setPassword(e.detail.value)}
                    required
                    disabled={loading}
                  />
                </IonItem>

                <IonButton
                  expand="block"
                  type="submit"
                  disabled={loading || !username || !password}
                >
                  {loading ? (
                    <IonSpinner name="crescent" />
                  ) : (
                    <>
                      <IonIcon icon={logInOutline} slot="start" />
                      Sign In
                    </>
                  )}
                </IonButton>
              </form>
            </IonCardContent>
          </IonCard>
        </div>
      </IonContent>
    </IonPage>
  );
};

export default LoginPage;

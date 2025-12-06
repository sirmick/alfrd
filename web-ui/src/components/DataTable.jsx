import { IonCard, IonCardHeader, IonCardTitle, IonCardContent } from '@ionic/react'

function DataTable({ data }) {
  if (!data || !data.columns || data.columns.length === 0) {
    return null
  }

  return (
    <IonCard>
      <IonCardHeader>
        <IonCardTitle>Flattened Data ({data.count} documents)</IonCardTitle>
      </IonCardHeader>
      <IonCardContent>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ 
            width: '100%', 
            borderCollapse: 'collapse',
            fontSize: '0.85em'
          }}>
            <thead>
              <tr style={{ backgroundColor: '#f5f5f5' }}>
                {data.columns.map((col, idx) => (
                  <th key={idx} style={{
                    padding: '8px',
                    textAlign: 'left',
                    borderBottom: '2px solid #ddd',
                    fontWeight: '600',
                    whiteSpace: 'nowrap'
                  }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, rowIdx) => (
                <tr key={rowIdx} style={{
                  borderBottom: '1px solid #eee'
                }}>
                  {data.columns.map((col, colIdx) => (
                    <td key={colIdx} style={{
                      padding: '8px',
                      maxWidth: '200px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      {row[col] !== null && row[col] !== undefined 
                        ? String(row[col]) 
                        : <span style={{ color: '#999' }}>—</span>
                      }
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ 
          marginTop: '10px', 
          fontSize: '0.8em', 
          color: '#666',
          textAlign: 'right' 
        }}>
          {data.count} row{data.count !== 1 ? 's' : ''} × {data.columns.length} column{data.columns.length !== 1 ? 's' : ''}
        </div>
      </IonCardContent>
    </IonCard>
  )
}

export default DataTable
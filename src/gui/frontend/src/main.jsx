import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import UI from '@workbench-ui'
import '@workbench-ui/style'
import './styles.css'

const root = document.getElementById('root')
root.classList.add('wb-workbench')
UI.setAppearance(root, { mode: 'dark', fontSize: 14 })
createRoot(root).render(<App />)

import { createContext, useContext } from 'react'

export const ExploreContext = createContext({ enabled: false, open: () => {} })

export const useExplore = () => useContext(ExploreContext)

export const KIND_GROUPS = {
  'To other banks': ['INTER'],
  'Within Dash': ['INTRA'],
  'Airtime & Data': ['Airtime', 'Data Bundle'],
  Betting: ['Betting & Lottery'],
  Bills: ['Utilities', 'Cable TV', 'Transport and Toll Payment'],
}

export const KIND_LABELS = {
  INTER: 'Transfer to other bank',
  INTRA: 'Transfer within Dash',
  Airtime: 'Airtime',
  'Data Bundle': 'Data',
  'Betting & Lottery': 'Betting',
  Utilities: 'Electricity & utilities',
  'Cable TV': 'Cable TV',
  'Transport and Toll Payment': 'Transport & tolls',
}

export const kindLabel = (kind) => KIND_LABELS[kind] ?? kind ?? 'Transaction'

export const list = (filters = {}) => ({ type: 'list', filters })
export const tx = (id) => ({ type: 'tx', id })
export const stuck = (phase, scope = '30d') => ({ type: 'onboarding', phase, scope })

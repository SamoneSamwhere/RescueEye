import { useShareOperation } from './useOperations'

/** Renders nothing: keeps this agency's operation visible to organizations working nearby. */
export function OperationsSync() {
  useShareOperation()
  return null
}

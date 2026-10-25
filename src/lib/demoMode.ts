/**
 * Demo mode: the built-in demo accounts (src/data/mockUsers.ts) and the mock
 * agencies, incidents, detections and drones that come with them.
 *
 * For presentations only. A production build (an LDRRMO pilot) leaves
 * VITE_DEMO_MODE unset, so nobody can sign in with a published demo password
 * and real users never see invented incidents beside real ones. The API has a
 * matching DEMO_MODE switch that must also be on for demo sign-in to work.
 */
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'

/** The mock seed when demo mode is on, nothing otherwise. */
export function demoSeed<T>(data: T[]): T[] {
  return DEMO_MODE ? data : []
}

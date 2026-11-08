// Shared frontend types. Mirror backend schemas here (app/schemas/).
export interface Health {
  status: string
  app: string
  env: string
}

/** With the API down, Next answers for it with a bare 500, so the status alone says nothing useful. */
export const NOT_ANSWERING = "The forecast API is not answering. Start it, and this page reconnects by itself.";

/** `status` is null when the API could not be reached at all. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** A viewing time outside the data will not fix itself. A lost connection might. */
  get isConnectionProblem(): boolean {
    return this.status === null || this.status >= 500;
  }
}

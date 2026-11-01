"use strict";
// A late response can finish, but can never replace a newer review state.
(function (root) {
  class LatestRequest {
    constructor() { this.serial = 0; this.controller = null; }
    cancel() { this.serial++; this.controller?.abort(); this.controller = null; }
    async run(task, accept, fail) {
      this.cancel();
      const serial = this.serial, controller = new AbortController();
      this.controller = controller;
      try {
        const value = await task(controller.signal);
        if (serial !== this.serial) return false;
        await accept(value);
        return true;
      } catch (error) {
        if (serial === this.serial && error.name !== "AbortError") await fail(error);
        return false;
      } finally {
        if (serial === this.serial) this.controller = null;
      }
    }
  }
  if (typeof module !== "undefined") module.exports = { LatestRequest };
  else root.MashiReviewState = { LatestRequest };
})(typeof window === "undefined" ? {} : window);

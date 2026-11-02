"use strict";
// Keep late responses out of current review and trace only saved crop inputs.
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
  function sameCrop(region, form) {
    return !!region && region.label === form.label && region.confirmed === form.confirmed &&
      Array.isArray(form.box) && form.box.length === 4 && Array.isArray(region.box) &&
      form.box.every((value, index) => String(value).trim() !== "" &&
        Number.isInteger(Number(value)) && Number(value) === region.box[index]);
  }
  function traceIssue(region, form) {
    if (!region?.active || region.coordinate_space === "generated-canvas") return "Choose a crop to trace.";
    if (!form.label || !form.confirmed) return "Confirm and save this crop before tracing.";
    if (!region.confirmed || !sameCrop(region, form)) return "Save the label and crop before tracing.";
    return "";
  }
  const api = {LatestRequest, sameCrop, traceIssue};
  if (typeof module !== "undefined") module.exports = api;
  else root.MashiReviewState = api;
})(typeof window === "undefined" ? {} : window);

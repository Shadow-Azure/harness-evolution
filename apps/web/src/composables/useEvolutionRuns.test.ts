// @vitest-environment jsdom

import type { EvolutionRunList } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { defineComponent } from "vue";

import { queryKeys } from "../api/queryKeys";
import { createAppQueryClient } from "../api/queryClient";
import { server } from "../test/server";
import { useEvolutionRuns } from "./useEvolutionRuns";

const response: EvolutionRunList = {
  running: [],
  history: [],
};

let client: QueryClient;
let model: ReturnType<typeof useEvolutionRuns>;
let wrapper: VueWrapper;

const Page = defineComponent({
  setup() {
    model = useEvolutionRuns();
    return () => null;
  },
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  server.use(
    http.get("/api/evolution/runs", () => HttpResponse.json(response)),
  );
  client = createAppQueryClient();
  wrapper = mount(Page, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  });
});
afterEach(() => {
  wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("useEvolutionRuns", () => {
  it("queries the stable evolution runs key", async () => {
    server.use(
      http.get("/api/evolution/runs", () => HttpResponse.json(response)),
    );

    await expect.poll(() => model.data.value).toEqual(response);
    expect(
      client.getQueryData(queryKeys.evolutionRuns),
    ).toEqual(response);
  });

});

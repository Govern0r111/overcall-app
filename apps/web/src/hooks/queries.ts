import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  api,
  Accuracy,
  ApiError,
  Issue,
  IssueDetail,
  IngestKey,
  LogEntry,
  LogFacets,
  Me,
  Overview,
  Page,
  Provider,
  RuleInfo,
  RunSummary,
  Settings,
} from "../lib/api";

const get = async <T,>(url: string, params?: object) => (await api.get<T>(url, { params })).data;
const clean = (o: Record<string, string | undefined>) =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v && v !== "all"));

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/v1/me"), refetchInterval: 15_000 });
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/v1/settings") });
export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/v1/overview"), refetchInterval: 15_000 });
export const useProviders = () =>
  useQuery({ queryKey: ["providers"], queryFn: () => get<Provider[]>("/v1/providers"), refetchInterval: 15_000 });
export const useIngestKeys = () =>
  useQuery({ queryKey: ["ingest-keys"], queryFn: () => get<Page<IngestKey>>("/v1/ingest-keys") });
export const useRules = () =>
  useQuery({ queryKey: ["rules"], queryFn: () => get<RuleInfo[]>("/v1/rules"), staleTime: Infinity });
export const useAccuracy = () => useQuery({ queryKey: ["accuracy"], queryFn: () => get<Accuracy>("/v1/accuracy") });
export const useLatestRun = () =>
  useQuery({
    queryKey: ["run"],
    queryFn: () =>
      get<RunSummary>("/v1/detection/runs/latest").catch((e: ApiError) =>
        e.code === "not_found" ? null : Promise.reject(e),
      ),
  });
export const useFacets = () => useQuery({ queryKey: ["facets"], queryFn: () => get<LogFacets>("/v1/logs/facets") });
export const useIssue = (id: string | null) =>
  useQuery({ queryKey: ["issue", id], queryFn: () => get<IssueDetail>(`/v1/issues/${id}`), enabled: !!id });

export interface IssueFilters {
  provider?: string;
  severity?: string;
  tier?: string;
}

export const useIssues = (f: IssueFilters) => {
  const params = clean({ ...f });
  return useInfiniteQuery({
    queryKey: ["issues", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => get<Page<Issue>>("/v1/issues", { ...params, limit: 25, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: 15_000,
  });
};

export interface LogFilters {
  provider?: string;
  status_class?: string;
  q?: string;
  endpoint?: string;
  model?: string;
  caller?: string;
  issue_id?: string;
  from?: string;
  to?: string;
}

export const useLogs = (f: LogFilters) => {
  const params = clean({ ...f });
  return useInfiniteQuery({
    queryKey: ["logs", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => get<Page<LogEntry>>("/v1/logs", { ...params, limit: 50, cursor: pageParam }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: 15_000,
  });
};

const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : "Something went wrong.");

const useAction = <T, A = void>(fn: (a: A) => Promise<T>, ok: (r: T) => string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      toast.success(ok(r));
      qc.invalidateQueries();
    },
    onError: fail,
  });
};

export const useLoadDemo = () =>
  useAction(
    async () => (await api.post<{ inserted: number }>("/v1/demo/load", { seed: 42, days: 7 })).data,
    (d) => `Loaded ${d.inserted} demo requests and ran detection.`,
  );
export const useDeleteDemo = () =>
  useAction(async () => (await api.delete("/v1/demo")).data, () => "Demo data deleted.");
export const useDeleteAllData = () =>
  useAction(async () => (await api.delete("/v1/data")).data, () => "All logs and issues deleted.");
export const useRunDetection = () =>
  useAction(
    async () => (await api.post<RunSummary>("/v1/detection/run")).data,
    (r) => {
      const n = Object.values(r.issue_counts).reduce((a, b) => a + b, 0);
      return `Detection finished: ${n} issue${n === 1 ? "" : "s"} across ${r.request_count} requests.`;
    },
  );

export const useSaveSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (s: Settings) => (await api.put<Settings>("/v1/settings", s)).data,
    onSuccess: (s) => {
      qc.setQueryData(["settings"], s);
      qc.invalidateQueries();
      toast.success("Settings saved. Run detection to apply the new thresholds.");
    },
    onError: fail,
  });
};

export const useResetSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<Settings>("/v1/settings/reset")).data,
    onSuccess: (s) => {
      qc.setQueryData(["settings"], s);
      toast.success("Settings reset to defaults.");
    },
    onError: fail,
  });
};

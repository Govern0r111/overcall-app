import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, Evaluation, Issue, LogEntry, Overview, Provider, Rule, Settings } from "../lib/api";

const get = async <T,>(url: string, params?: object) => (await api.get<T>(url, { params })).data;

export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/settings") });

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: () => get<Overview>("/overview"), refetchInterval: 15_000 });

export interface IssueFilters {
  provider?: string;
  severity?: string;
  tier?: string;
}

export const useIssues = (f: IssueFilters) => {
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v && v !== "all"));
  return useQuery({ queryKey: ["issues", params], queryFn: () => get<Issue[]>("/issues", params), refetchInterval: 15_000 });
};

export const useProviders = () => useQuery({ queryKey: ["providers"], queryFn: () => get<Provider[]>("/providers") });
export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: () => get<Rule[]>("/rules"), staleTime: Infinity });
export const useEvaluation = () => useQuery({ queryKey: ["evaluate"], queryFn: () => get<Evaluation>("/synthetic/evaluate") });

export interface LogFilters {
  search?: string;
  provider?: string;
  status_class?: string;
  endpoint?: string;
}

export const useLogs = (filters: LogFilters) => {
  const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
  return useQuery({
    queryKey: ["logs", params],
    queryFn: () => get<LogEntry[]>("/logs", params),
    refetchInterval: 15_000,
  });
};

const useRefreshData = () => {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ predicate: (q) => !["settings", "rules"].includes(q.queryKey[0] as string) });
};

export const useLoadSynthetic = () => {
  const refresh = useRefreshData();
  return useMutation({
    mutationFn: async (seed: number = 42) => (await api.post("/synthetic/load", { seed, days: 7 })).data,
    onSuccess: (d) => {
      refresh();
      toast.success(`Loaded ${d.inserted.toLocaleString()} synthetic requests (seed ${d.seed})`);
    },
    onError: () => toast.error("Couldn't load synthetic data. Please try again."),
  });
};

export const useClearData = () => {
  const refresh = useRefreshData();
  return useMutation({
    mutationFn: async () => (await api.delete("/data")).data,
    onSuccess: (d) => {
      refresh();
      toast.success(`Cleared ${d.deleted.toLocaleString()} logged requests`);
    },
  });
};

export const useRerun = () => {
  const refresh = useRefreshData();
  return useMutation({ mutationFn: async () => (await api.post("/detect/run")).data, onSuccess: () => refresh() });
};

export const useSaveSettings = () => {
  const qc = useQueryClient();
  const refresh = useRefreshData();
  return useMutation({
    mutationFn: async (s: Settings) => (await api.put<Settings>("/settings", s)).data,
    onMutate: (s) => qc.setQueryData(["settings"], s),
    onSuccess: (s) => {
      qc.setQueryData(["settings"], s);
      refresh();
    },
    onError: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.error("Couldn't save settings. Check the values and try again.");
    },
  });
};

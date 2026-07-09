"use client";

import { useDevUser } from "@/components/providers/dev-user-provider";

export function UserPicker() {
  const { users, selectedUserId, setSelectedUserId, isLoading, error } = useDevUser();
  const status = isLoading ? "checking" : error ? "offline" : "online";
  const tone =
    status === "online" ? "text-success" : status === "offline" ? "text-danger" : "text-faint";
  const dot =
    status === "online" ? "bg-success" : status === "offline" ? "bg-danger" : "bg-faint";

  return (
    <div className="flex min-w-0 items-center gap-4">
      <span className={`hidden items-center gap-2 font-mono text-xs md:flex ${tone}`}>
        <span className={`inline-block h-[7px] w-[7px] rounded-full ${dot}`} />
        {status === "checking" ? "API …" : status === "online" ? "API online" : "API offline"}
      </span>
      <label className="flex min-w-0 items-center gap-2.5 rounded-full border border-silver/[0.18] py-1.5 pl-1.5 pr-3">
        <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-silver-mark text-xs font-bold text-background">
          D
        </span>
        <span className="hidden text-sm text-silver sm:inline">Dev user</span>
        <select
          aria-label="Dev user"
          className="h-8 max-w-[200px] rounded-full bg-transparent text-sm text-text outline-none transition focus:text-accent"
          disabled={isLoading || users.length === 0}
          value={selectedUserId ?? ""}
          onChange={(event) => setSelectedUserId(event.target.value)}
        >
          {isLoading ? <option>Loading users</option> : null}
          {!isLoading && users.length === 0 ? <option>No users</option> : null}
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.email}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

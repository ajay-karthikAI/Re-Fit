"use client";

import { useDevUser } from "@/components/providers/dev-user-provider";

export function UserPicker() {
  const { users, selectedUserId, setSelectedUserId, isLoading, error } = useDevUser();

  return (
    <label className="flex min-w-0 items-center gap-2 text-sm text-subdued">
      <span className="hidden sm:inline">Dev user</span>
      <select
        aria-label="Dev user"
        className="h-9 max-w-[220px] rounded-md border border-border bg-surface px-3 text-sm text-text outline-none transition focus:border-accent"
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
      {error ? <span className="hidden text-xs text-red-300 md:inline">API offline</span> : null}
    </label>
  );
}

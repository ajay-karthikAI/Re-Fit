"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { type DevUser, listUsers } from "@/lib/api";

type DevUserContextValue = {
  users: DevUser[];
  selectedUser: DevUser | null;
  selectedUserId: string | null;
  setSelectedUserId: (id: string) => void;
  isLoading: boolean;
  error: Error | null;
};

const STORAGE_KEY = "refit.devUserId";
const DevUserContext = createContext<DevUserContextValue | null>(null);

// DEV AUTH: replace in Phase 3.
export function DevUserProvider({ children }: { children: React.ReactNode }) {
  const [selectedUserId, setSelectedUserIdState] = useState<string | null>(null);
  const usersQuery = useQuery({
    queryKey: ["dev-users"],
    queryFn: listUsers
  });

  useEffect(() => {
    setSelectedUserIdState(window.localStorage.getItem(STORAGE_KEY));
  }, []);

  useEffect(() => {
    if (!usersQuery.data?.length) {
      return;
    }
    const currentId = selectedUserId;
    const currentExists = usersQuery.data.some((user) => user.id === currentId);
    if (!currentId || !currentExists) {
      const nextId = usersQuery.data[0].id;
      window.localStorage.setItem(STORAGE_KEY, nextId);
      setSelectedUserIdState(nextId);
    }
  }, [selectedUserId, usersQuery.data]);

  const setSelectedUserId = (id: string) => {
    window.localStorage.setItem(STORAGE_KEY, id);
    setSelectedUserIdState(id);
  };

  const value = useMemo<DevUserContextValue>(() => {
    const users = usersQuery.data ?? [];
    return {
      users,
      selectedUser: users.find((user) => user.id === selectedUserId) ?? null,
      selectedUserId,
      setSelectedUserId,
      isLoading: usersQuery.isLoading,
      error: usersQuery.error
    };
  }, [selectedUserId, usersQuery.data, usersQuery.error, usersQuery.isLoading]);

  return <DevUserContext.Provider value={value}>{children}</DevUserContext.Provider>;
}

export function useDevUser() {
  const context = useContext(DevUserContext);
  if (context === null) {
    throw new Error("useDevUser must be used within DevUserProvider");
  }
  return context;
}

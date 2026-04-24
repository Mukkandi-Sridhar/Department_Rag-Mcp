export const state = {
  user: null,
};


export function setUser(user) {
  state.user = user;
}

export function currentUid() {
  return state.user?.uid || null;
}

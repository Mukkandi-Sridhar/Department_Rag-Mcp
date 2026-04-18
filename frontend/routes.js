export const routes = {
  home: "/",
  login: "/login",
  dashboard: "/dashboard",
  profile: "/profile",
  documents: "/documents",
};


export function goTo(path) {
  if (window.location.pathname !== path) {
    window.location.assign(path);
  }
}

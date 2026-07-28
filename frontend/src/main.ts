import { createApp } from 'vue';
import { createAuth0 } from '@auth0/auth0-vue';
import './main.css';
import App from './App.vue';
import router from './router';

const app = createApp(App);

app.use(router);

app.use(
  createAuth0({
    domain: import.meta.env.VITE_AUTH0_DOMAIN,
    clientId: import.meta.env.VITE_AUTH0_CLIENT_ID,
    authorizationParams: {
      redirect_uri: window.location.origin,
      audience: import.meta.env.VITE_AUTH0_AUDIENCE,
    },
    // Persist tokens across page refreshes (default is in-memory, which loses
    // the session on every reload) and enable silent refresh via refresh tokens
    // so short-lived access tokens are renewed without a full login redirect.
    cacheLocation: 'localstorage',
    useRefreshTokens: true,
  }),
);

app.mount('#app');

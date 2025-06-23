module.exports = {
  api: {
    input: {
      target: 'http://localhost:8000/api/schema/orval/',
    },
    output: {
      target: './frontend/src/api/client.ts',
      client: 'react-query',
      mode: 'split',
      prettier: true,
      mock: false,
      override: {
        useNativeEnums: true,
        mutator: {
          path: './frontend/src/api/axios.ts',
          name: 'axiosInstance',
        },
        query: {
          options: {
            retry: (failureCount, error) => {
              if (error?.response?.status === 404 || error?.response?.status === 403) {
                // Fail fast on 404 and 403
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      },
    },
  },
};

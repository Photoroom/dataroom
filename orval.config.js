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
        enumGenerationType: 'enum',
        mutator: {
          path: './frontend/src/api/axios.ts',
          name: 'axiosInstance',
        },
        query: {
          options: {
            retry: (failureCount, error) => {
              // Type guard for axios error
              if (error && typeof error === 'object' && 'response' in error && error.response && typeof error.response === 'object' && 'status' in error.response) {
                const status = error.response.status;
                if (status === 404 || status === 403) {
                  // Fail fast on 404 and 403
                  return false;
                }
              }
              return failureCount < 2;
            },
          },
        },
      },
    },
    hooks: {
      afterAllFilesWrite: ['./orval/fix-enums.sh', 'prettier --write'],
    },
  },
};

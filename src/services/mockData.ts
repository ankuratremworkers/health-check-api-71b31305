export const mockData = {
  "models": {
    "Health": [
      {
        "status": "active"
      },
      {
        "status": "active"
      },
      {
        "status": "active"
      }
    ]
  },
  "endpoints": {
    "GET /api/health": [
      {
        "status": "active"
      },
      {
        "status": "active"
      },
      {
        "status": "active"
      }
    ]
  }
} as const;

export type MockData = typeof mockData;

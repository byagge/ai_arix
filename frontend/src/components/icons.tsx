import { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 16, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      shapeRendering="geometricPrecision"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconHome = (p: P) => (
  <Svg {...p}>
    <path d="M3 10.2 12 3.5l9 6.7V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />
  </Svg>
);

export const IconChat = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
  </Svg>
);

export const IconAudio = (p: P) => (
  <Svg {...p}>
    <path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4" />
  </Svg>
);

export const IconImage = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <circle cx="8.5" cy="9.5" r="1.6" />
    <path d="m4 17 4.5-4.5L13 17l3-3 4 4" />
  </Svg>
);

export const IconModel = (p: P) => (
  <Svg {...p}>
    <path d="M12 3 4 7.2v9.6L12 21l8-4.2V7.2z" />
    <path d="M4 7.2 12 11.5l8-4.3M12 11.5V21" />
  </Svg>
);

export const IconKey = (p: P) => (
  <Svg {...p}>
    <circle cx="8" cy="15" r="4" />
    <path d="m11 12 8-8 2.5 2.5M17 6.5 19 8.5" />
  </Svg>
);

export const IconUsage = (p: P) => (
  <Svg {...p}>
    <path d="M3 17.5 9.5 11l4 4L21 7" />
    <path d="M15.5 7H21v5.5" />
  </Svg>
);

export const IconLogs = (p: P) => (
  <Svg {...p}>
    <path d="M3 7h18M3 12h18M3 17h18" />
  </Svg>
);

export const IconThreads = (p: P) => (
  <Svg {...p}>
    <path d="M4 6h6M14 6h6M4 12h11M19 12h1M4 18h4M12 18h8" />
    <circle cx="12" cy="6" r="1.6" />
    <circle cx="17" cy="12" r="1.6" />
    <circle cx="10" cy="18" r="1.6" />
  </Svg>
);

export const IconStorage = (p: P) => (
  <Svg {...p}>
    <ellipse cx="12" cy="6" rx="8" ry="3" />
    <path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
  </Svg>
);

export const IconPlugin = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="3.5" />
  </Svg>
);

export const IconSettings = (p: P) => (
  <Svg {...p}>
    <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
    <circle cx="16" cy="7" r="2.2" />
    <circle cx="10" cy="17" r="2.2" />
  </Svg>
);

export const IconMore = (p: P) => (
  <Svg {...p}>
    <circle cx="5" cy="12" r="1.1" fill="currentColor" />
    <circle cx="12" cy="12" r="1.1" fill="currentColor" />
    <circle cx="19" cy="12" r="1.1" fill="currentColor" />
  </Svg>
);

export const IconSearch = (p: P) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.6-3.6" />
  </Svg>
);

export const IconPanel = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M9.5 4v16" />
  </Svg>
);

export const IconChevronUpDown = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="m7 15 5 5 5-5M7 9l5-5 5 5" />
  </Svg>
);

export const IconChevronDown = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);

export const IconChevronLeft = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="m15 6-6 6 6 6" />
  </Svg>
);

export const IconChevronRight = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);

export const IconPlus = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const IconX = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);

export const IconCard = (p: P) => (
  <Svg {...p}>
    <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
    <path d="M2.5 10h19" />
  </Svg>
);

export const IconBook = (p: P) => (
  <Svg {...p}>
    <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H19v18H5.5A1.5 1.5 0 0 1 4 19.5z" />
    <path d="M8 3v18" />
  </Svg>
);

export const IconCode = (p: P) => (
  <Svg {...p}>
    <path d="m9 8-5 4 5 4M15 8l5 4-5 4" />
  </Svg>
);

export const IconCompare = (p: P) => (
  <Svg {...p}>
    <path d="m12 3 1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" />
    <path d="M18.5 16.5 19.4 19l2.1.8-2.1.9-.9 2.3-.9-2.3-2.1-.9 2.1-.8z" />
  </Svg>
);

export const IconSend = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Svg>
);

export const IconMonitor = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="13" rx="2" />
    <path d="M8 21h8M12 17v4" />
  </Svg>
);

export const IconSun = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M2 12h2M20 12h2M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5" />
  </Svg>
);

export const IconMoon = (p: P) => (
  <Svg {...p}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5" />
  </Svg>
);

export const IconExternal = (p: P) => (
  <Svg {...p}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Svg>
);

export const IconCheck = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Svg>
);

export const IconWarning = (p: P) => (
  <Svg {...p}>
    <path d="M12 3.5 22 20H2z" />
    <path d="M12 9.5v5M12 17.2v.3" />
  </Svg>
);

export const IconDoc = (p: P) => (
  <Svg {...p}>
    <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z" />
    <path d="M14 3v4h4" />
  </Svg>
);

export const IconRefresh = (p: P) => (
  <Svg {...p}>
    <path d="M20 12a8 8 0 1 1-2.6-5.9" />
    <path d="M20 4v4.5h-4.5" />
  </Svg>
);

export const IconTrash = (p: P) => (
  <Svg {...p}>
    <path d="M4 7h16M9 7V4.5h6V7M6.5 7l.8 13h9.4l.8-13" />
  </Svg>
);

export const IconBatches = (p: P) => (
  <Svg {...p}>
    <path d="M8 4H6.5A1.5 1.5 0 0 0 5 5.5v13A1.5 1.5 0 0 0 6.5 20H8M16 4h1.5A1.5 1.5 0 0 1 19 5.5v13a1.5 1.5 0 0 1-1.5 1.5H16" />
    <path d="M12 9v6" />
  </Svg>
);

export const IconUser = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="3.5" />
    <path d="M5.5 19.5c1.4-3.2 3.7-4.8 6.5-4.8s5.1 1.6 6.5 4.8" />
  </Svg>
);

export const IconArrowRight = (p: P) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);

export const IconUsers = (p: P) => (
  <Svg {...p}>
    <circle cx="9" cy="8" r="3" />
    <path d="M3.5 18.5c1-2.4 2.7-3.6 5.5-3.6s4.5 1.2 5.5 3.6" />
    <circle cx="17" cy="9" r="2.4" />
    <path d="M14.2 18.5c.7-1.6 1.9-2.4 3.8-2.4 1.4 0 2.5.5 3.2 1.4" />
  </Svg>
);

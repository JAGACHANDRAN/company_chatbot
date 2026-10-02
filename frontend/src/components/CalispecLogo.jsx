import React from 'react';

/**
 * Official Calispec chatbot Vector Logo Component.
 * Features Gear & Dial Symbol with 'Calispec' and 'chatbot' (only C capitalized).
 */
export default function CalispecLogo({ className = 'h-10 sm:h-11 md:h-12 w-auto' }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 460 140"
      className={className}
      fill="none"
      role="img"
      aria-label="Calispec chatbot"
    >
      <defs>
        <filter id="calispecHologramGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="0" stdDeviation="6" floodColor="#00f2fe" floodOpacity="0.6" />
        </filter>
      </defs>

      <g transform="translate(10, 10)">
        {/* GEAR ICON (BLUE) */}
        <path
          fill="#0072CE"
          d="M 68 8 
             A 52 52 0 0 1 78 8 
             L 81 22 
             A 50 50 0 0 1 93 27 
             L 105 18 
             A 52 52 0 0 1 112 25 
             L 107 38 
             A 50 50 0 0 1 117 49 
             L 130 48 
             A 52 52 0 0 1 133 58 
             L 121 65 
             A 50 50 0 0 1 121 78 
             L 133 85 
             A 52 52 0 0 1 130 95 
             L 117 94 
             A 50 50 0 0 1 107 105 
             L 112 118 
             A 52 52 0 0 1 105 125 
             L 93 116 
             A 50 50 0 0 1 81 121 
             L 78 135 
             A 52 52 0 0 1 68 135 
             L 65 121 
             A 50 50 0 0 1 53 116 
             L 41 125 
             A 52 52 0 0 1 34 118 
             L 39 105 
             A 50 50 0 0 1 29 94 
             L 16 95 
             A 52 52 0 0 1 13 85 
             L 25 78 
             A 50 50 0 0 1 25 65 
             L 13 58 
             A 52 52 0 0 1 16 48 
             L 29 49 
             A 50 50 0 0 1 39 38 
             L 34 25 
             A 52 52 0 0 1 41 18 
             L 53 27 
             A 50 50 0 0 1 65 22 
             Z
             M 73 30 
             A 42 42 0 1 0 73 114 
             A 42 42 0 1 0 73 30 Z"
        />

        {/* SPEEDOMETER DIAL & NEEDLE (ORANGE) */}
        <g transform="translate(73, 72)">
          {/* Arc ticks */}
          <path
            stroke="#E66000"
            strokeWidth="2.5"
            strokeLinecap="round"
            fill="none"
            d="M -30 -10 A 32 32 0 0 1 10 -30"
          />
          <line x1="-28" y1="-12" x2="-23" y2="-10" stroke="#E66000" strokeWidth="2.5" />
          <line x1="-18" y1="-24" x2="-15" y2="-19" stroke="#E66000" strokeWidth="2.5" />
          <line x1="-2" y1="-30" x2="-2" y2="-24" stroke="#E66000" strokeWidth="2.5" />
          <line x1="12" y1="-27" x2="9" y2="-22" stroke="#E66000" strokeWidth="2.5" />

          {/* Needle */}
          <polygon points="0,2 -24,-14 -18,-20" fill="#E66000" />
        </g>

        {/* CALISPEC WORD IN LOGO: 'Calispec' with only C capital */}
        <text
          x="126"
          y="78"
          fontFamily="'Inter', 'Space Grotesk', -apple-system, sans-serif"
          fontWeight="500"
          fontSize="48"
          fill="#0072CE"
          letterSpacing="0.5"
        >
          Calispec
        </text>

        {/* TAGLINE: 'chatbot' in lowercase (only C alone is capital) */}
        <text
          x="128"
          y="108"
          fontFamily="'Inter', -apple-system, sans-serif"
          fontWeight="700"
          fontStyle="italic"
          fontSize="20"
          fill="#E66000"
          letterSpacing="0.5"
        >
          chatbot
        </text>
      </g>
    </svg>
  );
}

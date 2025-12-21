'use client';

interface DimaticLogoProps {
    size?: number;
    className?: string;
}

export function DimaticLogo({ size = 32, className = '' }: DimaticLogoProps) {
    return (
        <div
            className={`flex items-center justify-center ${className}`}
            style={{ width: size, height: size }}
        >
            {/* Simple styled D logo - replace with actual logo asset */}
            <svg
                viewBox="0 0 32 32"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="w-full h-full"
            >
                <rect width="32" height="32" rx="8" className="fill-primary" />
                <text
                    x="16"
                    y="22"
                    textAnchor="middle"
                    className="fill-primary-foreground font-bold"
                    fontSize="18"
                >
                    D
                </text>
            </svg>
        </div>
    );
}

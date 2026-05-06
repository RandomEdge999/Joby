"use client";

import Image from "next/image";

type BrandLogoProps = {
  className?: string;
  priority?: boolean;
  alt?: string;
};

export default function BrandLogo({
  className = "h-10 w-auto",
  priority = false,
  alt = "Joby",
}: BrandLogoProps) {
  return (
    <Image
      src="/brand/logo.svg"
      alt={alt}
      width={2048}
      height={938}
      priority={priority}
      sizes="(max-width: 768px) 140px, 200px"
      className={className}
    />
  );
}

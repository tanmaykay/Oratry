"use client";
import type { ButtonHTMLAttributes, ReactNode } from "react";
export function Button({ children, variant = "primary", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" }) { return <button className={`button ${variant}`} {...props}>{children}</button>; }
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section>; }
export function Eyebrow({ children }: { children: ReactNode }) { return <p className="eyebrow">{children}</p>; }
export function Score({ value }: { value: number }) { return <span className="score">{value}<small>/100</small></span>; }
export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) { return <div className="empty"><h2>{title}</h2><p>{body}</p>{action}</div>; }

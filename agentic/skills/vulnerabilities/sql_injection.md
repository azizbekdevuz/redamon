# SQL Injection Testing Guide - Summary

This comprehensive resource documents SQL injection attack surface, detection channels, and DBMS-specific exploitation techniques across MySQL, PostgreSQL, MSSQL, and Oracle databases.

## Key Attack Vectors

The guide identifies multiple injection points: "Path/query/body/header/cookie" and emphasizes that modern attacks exploit "parser differentials, ORM/query-builder edges, JSON/XML/CTE/JSONB surfaces."

## Detection Approaches

Four primary channels are outlined:
- **Error-Based**: Provoke database errors revealing system information
- **Boolean-Based**: Diff responses based on predicate truth values
- **Time-Based**: Leverage database sleep functions for inference
- **Out-of-Band**: Use DNS/HTTP callbacks via database primitives

## Critical Vulnerabilities

UNION-based extraction requires "column count and types via ORDER BY n and UNION SELECT null." Blind extraction employs "SUBSTRING/ASCII" or JSON operators with binary search optimization. The guide warns that "whereRaw/orderByRaw" in ORMs represent dangerous APIs.

## Testing Methodology

The recommended approach involves six sequential steps: identify query structure, determine input influence, confirm injection class, select the optimal oracle, establish extraction channel, then pivot toward metadata and high-value targets.

## Core Defense

The guidance concludes: parameterization is essential, dynamic identifiers should be avoided, and validation must occur "at the exact boundary where user input meets SQL."

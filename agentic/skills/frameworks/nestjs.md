# NestJS Security Testing Playbook Summary

This comprehensive guide addresses security vulnerabilities in NestJS applications across multiple dimensions:

## Core Attack Surfaces

The playbook identifies critical areas including decorator pipelines (guards, pipes, interceptors), module boundaries, and multi-transport authentication. It emphasizes that "Guards execute: global → controller → method" and missing guards on individual handlers represent a primary vulnerability class.

## High-Priority Targets

Key endpoints deserve immediate attention: Swagger/OpenAPI endpoints in production, authentication handlers, admin-decorated controllers, file upload functionality, and WebSocket gateways. The guide notes that "microservice handlers often lack guards (considered internal)" despite potential exposure.

## Vulnerability Categories

**Guard Bypass Issues**: Missing `@UseGuards` decorators on new methods, `@Public()` metadata applied too broadly, and guards failing silently across different execution contexts (HTTP vs. WebSocket vs. RPC).

**Validation Gaps**: The `ValidationPipe` can be circumvented through missing `forbidNonWhitelisted: true`, absent `@Type()` decorators on nested objects, and `transform: true` enabling dangerous type coercion.

**Auth Weaknesses**: JWT misconfigurations (ignored expiration, weak secrets), Passport strategy returning full database records, and missing `ClassSerializerInterceptor` exposing sensitive fields.

**ORM Injection**: Template literal interpolation in QueryBuilder, operator injection in Mongoose, and unsafe Prisma raw queries.

## Testing Methodology

The framework recommends: enumerating endpoints via Swagger, auditing decorator stacks per method, matrix testing across authentication levels and transports, probing validation boundaries, and checking serialization consistency.
